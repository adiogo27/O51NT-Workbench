from __future__ import annotations

import asyncio
import time

import pytest

from app.services.scraper import (
    BACKOFF_TTLS,
    EthicalScraper,
    MemoryBackoffStore,
    RateLimiter,
    SqliteBackoffStore,
    extrair_convites,
    extrair_hashtags,
)
from tests.conftest import FakeFetcher

pytestmark = pytest.mark.unit


def novo(fetcher: FakeFetcher, **kw) -> EthicalScraper:  # noqa: ANN003
    kw.setdefault("backoff", MemoryBackoffStore())
    return EthicalScraper(intervalo=kw.pop("intervalo", 0), fetcher_estatico=fetcher, fetcher_js=fetcher, **kw)


async def test_respeita_robots_txt() -> None:
    f = FakeFetcher({"https://ex.com/robots.txt": (200, "User-agent: *\nDisallow: /privado")})
    s = novo(f)
    r = await s.buscar("https://ex.com/privado/x")
    assert r.erro == "bloqueado por robots.txt"
    assert "https://ex.com/privado/x" not in f.chamadas
    await s.stop()


async def test_robots_permitido_e_hash() -> None:
    f = FakeFetcher({"https://ex.com/robots.txt": (200, "User-agent: *\nDisallow: /privado"), "https://ex.com/ok": (200, "<p>oi</p>")})
    s = novo(f)
    r = await s.buscar("https://ex.com/ok")
    assert r.ok and len(r.sha256) == 64 and r.coletado_em
    await s.stop()


async def test_robots_erro_5xx_bloqueia_conservador() -> None:
    f = FakeFetcher({"https://ex.com/robots.txt": (503, "")})
    s = novo(f)
    assert (await s.buscar("https://ex.com/a")).erro == "bloqueado por robots.txt"
    await s.stop()


@pytest.mark.parametrize("status", [403, 429])
async def test_403_429_coloca_dominio_em_backoff(status: int) -> None:
    f = FakeFetcher({"https://ex.com/a": (status, ""), "https://ex.com/b": (200, "ok")})
    s = novo(f)
    r1 = await s.buscar("https://ex.com/a")
    r2 = await s.buscar("https://ex.com/b")
    assert "backoff" in (r1.erro or "")
    assert "backoff" in (r2.erro or "")
    assert "https://ex.com/b" not in f.chamadas
    await s.stop()


def test_backoff_ttl_exponencial_memoria() -> None:
    from datetime import UTC, datetime, timedelta

    b = MemoryBackoffStore()
    agora = datetime.now(UTC)
    duracoes = []
    for _ in range(4):
        duracoes.append(b.registrar("ex.com", 429) - agora)
    esperado = [timedelta(hours=1), timedelta(hours=6), timedelta(hours=24), timedelta(hours=24)]
    assert [round(d.total_seconds() / 3600) for d in duracoes] == [round(e.total_seconds() / 3600) for e in esperado]
    assert BACKOFF_TTLS[-1] == timedelta(hours=24)
    b.limpar("ex.com")
    assert b.bloqueado_ate("ex.com") is None


def test_backoff_sqlite_persiste_e_expira(data_dir) -> None:  # noqa: ANN001
    from datetime import UTC, datetime, timedelta

    from freezegun import freeze_time

    from app import db

    db.init_db()
    b = SqliteBackoffStore()
    ate1 = b.registrar("ex.com", 403)
    assert b.bloqueado_ate("ex.com") is not None
    ate2 = SqliteBackoffStore().registrar("ex.com", 403)  # nova instância = "reinício"
    assert ate2 - ate1 > timedelta(hours=4)
    assert b.listar()["ex.com"]["nivel"] == 2
    with freeze_time(datetime.now(UTC) + timedelta(hours=7)):
        assert b.bloqueado_ate("ex.com") is None


async def test_sucesso_apos_ttl_zera_backoff() -> None:
    f = FakeFetcher({"https://ex.com/a": (200, "ok")})
    b = MemoryBackoffStore()
    b.registrar("ex.com", 429)
    b._d["ex.com"] = (b._d["ex.com"][0].replace(year=2000), 1, 429)  # TTL vencido
    s = novo(f, backoff=b)
    assert (await s.buscar("https://ex.com/a")).ok
    assert b.listar() == {}
    await s.stop()


async def test_retry_uma_vez_em_5xx() -> None:
    f = FakeFetcher({"https://ex.com/a": (500, "")})
    s = novo(f, retries=1)
    r = await s.buscar("https://ex.com/a")
    assert f.chamadas.count("https://ex.com/a") == 2
    assert r.erro == "HTTP 500"
    await s.stop()


async def test_rate_limiter_por_dominio() -> None:
    rl = RateLimiter(0.2)
    t0 = time.monotonic()
    await rl.aguardar("a.com")
    await rl.aguardar("b.com")  # outro domínio: não espera
    assert time.monotonic() - t0 < 0.1
    await rl.aguardar("a.com")
    assert time.monotonic() - t0 >= 0.19


async def test_fila_concorrente() -> None:
    f = FakeFetcher({f"https://d{i}.com/": (200, str(i)) for i in range(6)})
    s = novo(f, concorrencia=2)
    res = await asyncio.gather(*(s.buscar(f"https://d{i}.com/") for i in range(6)))
    assert [r.html for r in res] == [str(i) for i in range(6)]
    assert len(s._workers) == 2
    await s.stop()


def test_extrair_convites_ddg_encodado() -> None:
    html = (
        '<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fchat.whatsapp.com%2FAbCdEfGhIjKlMn&rut=1">x</a>'
        '<a href="https://t.me/joinchat/QWErty12345">t</a> https://t.me/+ZXCvbn98765 '
        "https://chat.whatsapp.com/AbCdEfGhIjKlMn"
    )
    assert extrair_convites(html) == [
        ("whatsapp", "https://chat.whatsapp.com/AbCdEfGhIjKlMn"),
        ("telegram", "https://t.me/joinchat/QWErty12345"),
        ("telegram", "https://t.me/+ZXCvbn98765"),
    ]


def test_extrair_hashtags_ignora_script_e_ancoras() -> None:
    html = "<ol><li>#Eleicoes2026</li><li>#PRF</li><li>#Eleicoes2026</li></ol><script>var a='#naoconta'</script><a href='#topo'>x</a>"
    assert extrair_hashtags(html) == {"#Eleicoes2026": 2, "#PRF": 1}


def test_extrair_convites_snippet_sem_esquema() -> None:
    texto = "entre no grupo chat.whatsapp.com/AbCdEfGhIjKlMn e t.me/joinchat/QWErty12345"
    assert [p for p, _ in extrair_convites(texto)] == ["whatsapp", "telegram"]
