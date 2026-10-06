from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from freezegun import freeze_time
from sqlmodel import Session, select

from app import db
from app.models.evidence import Evidence
from app.services import alerts, evidence_store, locations, scheduler

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------- scheduler
def test_validar_cron() -> None:
    scheduler.validar_cron("*/15 * * * *")
    for ruim in ("* * *", "61 * * * *", "abc"):
        with pytest.raises(ValueError):
            scheduler.validar_cron(ruim)


@freeze_time("2026-10-05 12:00:00")
def test_proxima_execucao() -> None:
    nxt = scheduler.proxima_execucao("0 */6 * * *")  # America/Sao_Paulo (UTC-3): 09:00 local → próxima 12:00 local
    assert nxt is not None and nxt.isoformat().startswith("2026-10-05T15:00")


# ---------------------------------------------------------------- alertas
def test_alerta_jsonl(data_dir: Path) -> None:
    caminho = alerts.gravar_jsonl({"a": 1})
    linhas = Path(caminho).read_text().splitlines()
    assert json.loads(linhas[-1]) == {"a": 1}


async def test_alerta_webhook_sem_url(data_dir: Path) -> None:
    assert await alerts.disparar("webhook", {}, None) == "webhook: URL não configurada"


async def test_alerta_webhook(data_dir: Path) -> None:
    import respx
    from httpx import Response

    with respx.mock:
        rota = respx.post("http://127.0.0.1:9/hook").mock(return_value=Response(204))
        assert await alerts.disparar("webhook", {"x": 1}, "http://127.0.0.1:9/hook") == "webhook: HTTP 204"
        assert rota.called


# ---------------------------------------------------------------- evidências
def _salvar(conteudo: bytes, nome: str = "a.txt") -> Evidence:
    db.init_db()
    rel, sha, tam = evidence_store.salvar(io.BytesIO(conteudo), nome, 10_000)
    ev = Evidence(arquivo=rel, sha256=sha, tamanho=tam, nome_original=nome)
    with Session(db.get_engine()) as s:
        s.add(ev)
        s.commit()
        s.refresh(ev)
    return ev


def test_evidencia_hash_e_verificacao(data_dir: Path) -> None:
    import hashlib

    ev = _salvar(b"conteudo")
    assert ev.sha256 == hashlib.sha256(b"conteudo").hexdigest()
    assert evidence_store.verificar(ev)["integro"]
    evidence_store.caminho_absoluto(ev).write_bytes(b"adulterado")
    assert not evidence_store.verificar(ev)["integro"]


def test_evidencia_limite(data_dir: Path) -> None:
    with pytest.raises(ValueError):
        evidence_store.salvar(io.BytesIO(b"x" * 20), "a", 10)
    assert not any(p.is_file() and p.name != "manifest.jsonl" for p in evidence_store.evidence_dir().rglob("*"))


def test_nome_seguro_impede_path_traversal(data_dir: Path) -> None:
    ev = _salvar(b"x", "../../etc/passwd")
    assert ".." not in ev.arquivo
    assert evidence_store.evidence_dir().resolve() in evidence_store.caminho_absoluto(ev).parents


def test_export_zip_com_manifest(data_dir: Path) -> None:
    ev = _salvar(b"abc")
    evidence_store.registrar_manifesto(ev)
    zf = zipfile.ZipFile(io.BytesIO(evidence_store.exportar_zip([ev])))
    nomes = zf.namelist()
    assert "manifest.json" in nomes and "SHA256SUMS" in nomes
    meta = json.loads(zf.read("manifest.json"))
    assert meta["itens"][0]["sha256"] == ev.sha256
    assert ev.sha256 in zf.read("SHA256SUMS").decode()
    assert evidence_store.manifesto_path().exists()


# ---------------------------------------------------------------- localidades
def test_localidades_busca_sem_acento() -> None:
    r = locations.buscar("sao paulo")
    assert {x["tipo"] for x in r} == {"uf", "capital"}


def test_localidades_rodovia_por_uf() -> None:
    r = locations.buscar(tipo="rodovia", uf="SC")
    assert any(x["nome"] == "BR-101" for x in r)
    assert locations.termo_busca(r[0]).startswith("(BR-")


# ---------------------------------------------------------------- scheduler reconstrói a partir de `monitor`
async def test_scheduler_reconstroi_jobs_da_tabela_monitor(data_dir: Path) -> None:
    from app.models.monitor import Monitor

    db.init_db()
    with Session(db.get_engine()) as s:
        ativo = Monitor(nome="a", query="PRF", cron="0 * * * *")
        pausado = Monitor(nome="p", query="PRF", cron="0 * * * *", ativo=False)
        s.add(ativo)
        s.add(pausado)
        s.commit()
        s.refresh(ativo)
    jobs_monitor = lambda s: [j.id for j in s.get_jobs() if j.id.startswith("monitor-")]  # noqa: E731  (o job "radar-ciclo" é global)
    sch = scheduler.iniciar()
    try:
        assert jobs_monitor(sch) == [f"monitor-{ativo.id}"]
        assert sch.get_job(scheduler.RADAR_JOB_ID) is not None  # radar agendado junto
        scheduler.desagendar(ativo.id)  # type: ignore[arg-type]
        assert jobs_monitor(sch) == []
    finally:
        scheduler.parar()
    sch = scheduler.iniciar()  # "reinício": reconstrói de novo a partir da tabela
    try:
        assert jobs_monitor(sch) == [f"monitor-{ativo.id}"]
    finally:
        scheduler.parar()


# ---------------------------------------------------------------- retenção do histórico
def test_podar_historico_por_idade_e_teto(data_dir: Path) -> None:
    from datetime import UTC, datetime, timedelta

    from app.models.query import QueryHistory
    from app.services.retention import podar_historico

    db.init_db()
    agora = datetime.now(UTC)
    with Session(db.get_engine()) as s:
        for i in range(5):
            s.add(QueryHistory(query=f"q{i}", criado_em=agora - timedelta(days=i * 50)))  # 0, 50, 100, 150, 200 dias
        s.commit()
        assert podar_historico(s, older_than_days=90) == 3
        assert podar_historico(s, max_entries=1) == 1
        assert [h.query for h in s.exec(select(QueryHistory)).all()] == ["q0"]


# ---------------------------------------------------------------- cliente SearXNG
async def test_searxng_client_json_e_hash(data_dir: Path) -> None:
    import httpx

    from app.services.searxng_client import SearxngClient

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.params["format"] == "json"
        assert req.url.params["engines"] == "duckduckgo,bing"
        return httpx.Response(200, json={"results": [{"url": "https://a.com", "title": "A", "content": "chat.whatsapp.com/AbCdEfGhIjKlMn"}]})

    c = SearxngClient(base_url="http://sx", transport=httpx.MockTransport(handler))
    r = await c.buscar("x", ["duckduckgo", "bing"])
    assert r.ok and len(r.sha256) == 64 and r.resultados[0]["url"] == "https://a.com"
    assert "chat.whatsapp.com" in r.texto_concatenado()
    await c.close()


async def test_searxng_client_retry_e_erros(data_dir: Path) -> None:
    import httpx

    from app.services.searxng_client import SearxngClient, SearxngIndisponivel

    chamadas = {"n": 0}

    def flaky(req: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        return httpx.Response(502)

    c = SearxngClient(base_url="http://sx", transport=httpx.MockTransport(flaky), retries=1)
    r = await c.buscar("x")
    assert chamadas["n"] == 2 and r.erro == "HTTP 502"
    c403 = SearxngClient(base_url="http://sx", transport=httpx.MockTransport(lambda _r: httpx.Response(403)))
    assert "json" in ((await c403.buscar("x")).erro or "")

    def recusa(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=req)

    off = SearxngClient(base_url="http://sx", transport=httpx.MockTransport(recusa))
    with pytest.raises(SearxngIndisponivel):
        await off.buscar("x")
    assert not await off.disponivel()


# ---------------------------------------------------------------- hashtags: acentos
@pytest.mark.parametrize(
    ("a", "b"),
    [("#Eleicoes2026", "#Eleições2026"), ("#Eleições2026", "#Eleicoes2026"), ("ELEIÇÕES2026", "#eleicoes2026"), ("#São_João", "#sao_joao")],
)
def test_chave_normalizada_ignora_acento_e_caixa(a: str, b: str) -> None:
    from app.services.hashtag_tracker import chave_normalizada

    assert chave_normalizada(a) == chave_normalizada(b)


def test_chave_normalizada_distingue_tags_diferentes() -> None:
    from app.services.hashtag_tracker import chave_normalizada

    assert chave_normalizada("#Eleicoes2026") != chave_normalizada("#Eleicoes2022")


def test_migration_adiciona_coluna_e_faz_backfill(data_dir: Path) -> None:
    from sqlalchemy import create_engine, text

    data_dir.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{data_dir / 'o51nt.db'}"
    legado = create_engine(url)
    with legado.begin() as c:  # esquema da v1.0 (sem chave_normalizada)
        c.execute(text("CREATE TABLE hashtag (id INTEGER PRIMARY KEY, tag VARCHAR NOT NULL, rede VARCHAR NOT NULL, contagem INTEGER NOT NULL, primeira_vez DATETIME NOT NULL, ultima_vez DATETIME NOT NULL, fonte VARCHAR NOT NULL, monitor_id INTEGER, UNIQUE (tag, rede))"))
        c.execute(text("INSERT INTO hashtag VALUES (1, '#Eleições2026', 'x', 3, '2026-10-01', '2026-10-01', 'trends24', NULL)"))
    legado.dispose()
    db.init_db()
    db.init_db()  # idempotente
    with db.get_engine().connect() as c:
        assert c.execute(text("SELECT chave_normalizada FROM hashtag WHERE id = 1")).scalar() == "#eleicoes2026"


async def test_coletar_soma_variantes_acentuadas(data_dir: Path) -> None:
    from app.services import hashtag_tracker
    from app.services.scraper import EthicalScraper, MemoryBackoffStore
    from tests.conftest import FakeFetcher

    db.init_db()
    f = FakeFetcher({"https://trends24.in/brazil/": (200, "<li>#Eleições2026</li><li>#Eleições2026</li><li>#ELEICOES2026</li><li>#PRF</li>")})
    s = EthicalScraper(intervalo=0, fetcher_estatico=f, fetcher_js=f, backoff=MemoryBackoffStore())
    with Session(db.get_engine()) as session:
        r = await hashtag_tracker.coletar(session, s, "#Eleicoes2026")
        assert r["ocorrencias_alvo"] == 3
        assert r["variantes_encontradas"] == ["#ELEICOES2026", "#Eleições2026"]
        tags = {v.tag for v in hashtag_tracker.variantes(session, "#eleições2026")}
        assert tags == {"#Eleicoes2026", "#Eleições2026", "#ELEICOES2026"}
    await s.stop()


# ---------------------------------------------------------------- SearXNG: log com timeout parcial (respx)
async def test_searxng_log_timeout_parcial_respx(data_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    import logging

    import respx
    from httpx import Response

    from app.services.searxng_client import SearxngClient

    caplog.set_level(logging.INFO, logger="o51nt.searxng")
    with respx.mock(base_url="http://sx") as mock:
        mock.get("/search").mock(
            return_value=Response(
                200,
                json={"results": [{"url": "https://a.com", "title": "A"}], "unresponsive_engines": [["duckduckgo", "timeout"]]},
            )
        )
        c = SearxngClient(base_url="http://sx")
        r = await c.buscar("x")
        await c.close()
    assert r.ok and r.engines_sem_resposta == [["duckduckgo", "timeout"]]
    rec = caplog.records[-1]
    assert rec.levelno == logging.WARNING
    assert rec.dados["engines_sem_resposta"] == [["duckduckgo", "timeout"]]  # type: ignore[attr-defined]
    assert "erro" not in rec.dados  # type: ignore[attr-defined]


async def test_searxng_log_sem_erro_nao_grava_chave(data_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    import logging

    import respx
    from httpx import Response

    from app.services.searxng_client import SearxngClient

    caplog.set_level(logging.INFO, logger="o51nt.searxng")
    with respx.mock(base_url="http://sx") as mock:
        mock.get("/search").mock(return_value=Response(200, json={"results": []}))
        c = SearxngClient(base_url="http://sx")
        await c.buscar("x")
        await c.close()
    dados = caplog.records[-1].dados  # type: ignore[attr-defined]
    assert "erro" not in dados and "engines_sem_resposta" not in dados
    assert caplog.records[-1].levelno == logging.INFO


async def test_searxng_erro_http_grava_texto_real(data_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    import respx
    from httpx import Response

    from app.services.searxng_client import SearxngClient

    with respx.mock(base_url="http://sx") as mock:
        mock.get("/search").mock(return_value=Response(400, text="Invalid  engine\n name"))
        c = SearxngClient(base_url="http://sx")
        r = await c.buscar("x")
        await c.close()
    assert r.erro == "HTTP 400: Invalid engine name"
    assert caplog.records[-1].dados["erro"] == "HTTP 400: Invalid engine name"  # type: ignore[attr-defined]
