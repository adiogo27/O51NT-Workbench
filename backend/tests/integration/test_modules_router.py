from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ---------------------------------------------------------------- sistema
def test_health_version(client: TestClient) -> None:
    assert client.get("/api/health").json()["db"] is True
    assert client.get("/api/version").json()["versao"] == "1.0.0"


def test_rota_api_inexistente_404(client: TestClient) -> None:
    assert client.get("/api/nao-existe").status_code == 404


# ---------------------------------------------------------------- monitores
def test_monitor_crud_e_run_now(client: TestClient, data_dir: Path) -> None:
    r = client.post("/api/monitors", json={"nome": "PRF", "query": "PRF after:2026-10-01", "cron": "*/30 * * * *"})
    assert r.status_code == 201
    mid = r.json()["id"]
    assert r.json()["proxima_execucao"]
    run = client.post(f"/api/monitors/{mid}/run-now").json()
    assert run["status"] == "ok" and "google" in run["deeplinks"]
    assert len(client.get(f"/api/monitors/{mid}/results").json()) == 1
    assert list((data_dir / "alerts").glob("*.jsonl"))
    r = client.patch(f"/api/monitors/{mid}", json={"ativo": False})
    assert r.json()["ativo"] is False and r.json()["proxima_execucao"] is None
    assert client.delete(f"/api/monitors/{mid}").status_code == 204
    assert client.get(f"/api/monitors/{mid}").status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"nome": "x", "query": "q", "cron": "bad"},
        {"nome": "x", "query": "q", "canal_alerta": "webhook"},
        {"nome": "x", "query": "q", "canal_alerta": "email"},
    ],
)
def test_monitor_validacoes(client: TestClient, payload: dict) -> None:
    assert client.post("/api/monitors", json=payload).status_code == 422


# ---------------------------------------------------------------- convites
def test_invites_queries(client: TestClient) -> None:
    r = client.get("/api/invites/queries", params={"termo": "eleições"}).json()
    assert r["queries"]["whatsapp"].endswith('(chat.whatsapp.com "eleições")')
    assert r["queries"]["telegram"].endswith('(t.me/joinchat "eleições")')
    assert r["deeplinks"]["whatsapp"]["google"].startswith("https://www.google.com/search?q=")


def test_invites_scan_export_delete(client: TestClient, fake_searxng) -> None:  # noqa: ANN001
    from app.routers.invites import montar_queries

    qs = montar_queries("blitz")
    fake_searxng.respostas[qs["whatsapp"]] = [
        {"url": "https://www.facebook.com/p/1", "title": "Grupo", "content": "entre: chat.whatsapp.com/AAAAABBBBBCCCCC"},
        {"url": "https://chat.whatsapp.com/DDDDDEEEEEFFFFF", "title": "", "content": ""},
    ]
    fake_searxng.respostas[qs["telegram"]] = [{"url": "https://x.com/s/1", "title": "t.me/joinchat/ZZZZZZZZZZ", "content": ""}]
    r = client.post("/api/invites/scan", json={"termo": "blitz"}).json()
    assert r["novos"] == 3
    assert {e["plataforma"]: e["encontrados"] for e in r["execucoes"]} == {"whatsapp": 2, "telegram": 1}
    assert all(e["fonte"] == "searxng:duckduckgo,bing,startpage" for e in r["execucoes"])
    r2 = client.post("/api/invites/scan", json={"termo": "blitz", "engines": ["duckduckgo"]}).json()
    assert r2["novos"] == 0 and r2["atualizados"] == 3
    lista = client.get("/api/invites").json()
    assert {i["plataforma"] for i in lista} == {"whatsapp", "telegram"}
    assert all(len(i["hash_conteudo"]) == 64 and "searxng.test" in i["origem"] for i in lista)
    csv_txt = client.get("/api/invites/export", params={"formato": "csv"}).text
    assert csv_txt.splitlines()[0].startswith("id,plataforma,url")
    assert len(json.loads(client.get("/api/invites/export", params={"formato": "json"}).text)) == 3
    assert client.delete(f"/api/invites/{lista[0]['id']}").status_code == 204
    assert len(client.get("/api/invites").json()) == 2


def test_invites_scan_searxng_erro_http(client: TestClient, fake_searxng) -> None:  # noqa: ANN001
    fake_searxng.status = 403
    r = client.post("/api/invites/scan", json={"termo": "x", "plataformas": ["telegram"]}).json()
    assert r["novos"] == 0 and "json" in r["execucoes"][0]["erro"]


# ---------------------------------------------------------------- ferramentas
def test_tools_catalogo_completo(client: TestClient) -> None:
    tools = client.get("/api/tools").json()
    urls = {t["url"] for t in tools}
    esperadas = {
        "https://github.com/dimdenGD/OldTweetDeck/",
        "https://onemilliontweetmap.com/",
        "https://trends24.in/brazil/",
        "https://whopostedwhat.com/",
        "https://sowsearch.info/",
        "https://www.google.com/imghp",
        "https://tineye.com/",
        "https://yandex.com/images",
        "https://platform.sensity.ai/login",
        "https://lenso.ai/pt",
        "https://chromewebstore.google.com/detail/search-by-image/cnojnbdhbhnkbcieeekonklommdnndci",
        "https://commentpicker.com/",
        "https://chromewebstore.google.com/detail/evidence-collector/mkloikhcnmoebenehakgkccipondapdk",
        "https://www.google.com.br/alerts",
        "https://programmablesearchengine.google.com/about/",
        "https://trends.google.com.br/trending",
    }
    assert esperadas <= urls


def test_tools_deeplink(client: TestClient) -> None:
    r = client.get("/api/tools/deeplink", params={"tool": "google_trends", "q": "PRF"}).json()
    assert r["url"].endswith("q=PRF") and r["prefill"]
    r = client.get("/api/tools/deeplink", params={"tool": "commentpicker", "q": "x"}).json()
    assert r["url"] == "https://commentpicker.com/" and not r["prefill"]
    assert client.get("/api/tools/deeplink", params={"tool": "nada"}).status_code == 404


# ---------------------------------------------------------------- evidências
def test_evidence_fluxo_completo(client: TestClient) -> None:
    r = client.post(
        "/api/evidence",
        files={"arquivo": ("print.txt", b"conteudo", "text/plain")},
        data={"origem_url": "https://ex.com/post", "notas": "n1"},
    )
    assert r.status_code == 201
    ev = r.json()
    assert ev["tipo"] == "arquivo" and len(ev["sha256"]) == 64
    dl = client.get(f"/api/evidence/{ev['id']}/download")
    assert dl.content == b"conteudo" and dl.headers["x-content-sha256"] == ev["sha256"]
    assert client.get(f"/api/evidence/{ev['id']}/verify").json()["integro"]
    assert client.patch(f"/api/evidence/{ev['id']}", json={"notas": "n2"}).json()["notas"] == "n2"
    z = zipfile.ZipFile(io.BytesIO(client.post("/api/evidence/export", json={"ids": []}).content))
    dup = client.post("/api/evidence", files={"arquivo": ("copia.txt", b"conteudo", "text/plain")}).json()
    bh = client.get(f"/api/evidence/by-hash/{ev['sha256'].upper()}").json()
    assert bh["total"] == 2 and bh["primeira_coleta"]["id"] == ev["id"]
    assert [o["id"] for o in bh["ocorrencias"]] == [ev["id"], dup["id"]]
    assert client.get("/api/evidence/by-hash/" + "0" * 64).status_code == 404
    assert client.get("/api/evidence/by-hash/xyz").status_code == 422
    client.delete(f"/api/evidence/{dup['id']}")
    assert "manifest.json" in z.namelist()
    assert client.delete(f"/api/evidence/{ev['id']}").status_code == 204
    assert client.get("/api/evidence").json() == []


# ---------------------------------------------------------------- hashtags
TRENDS_HTML = "<ol class='trend-card__list'><li>#Eleicoes2026</li><li>#PRF</li><li>#Eleicoes2026</li></ol>"


def test_hashtags_crud_queries(client: TestClient) -> None:
    r = client.post("/api/hashtags", json={"tag": "Eleicoes"})
    assert r.status_code == 201 and r.json()["tag"] == "#Eleicoes"
    assert client.post("/api/hashtags", json={"tag": "#Eleicoes"}).status_code == 409
    hid = r.json()["id"]
    assert client.patch(f"/api/hashtags/{hid}", json={"contagem": 7}).json()["contagem"] == 7
    q = client.get("/api/hashtags/queries", params={"tag": "PRF"}).json()
    assert q["query"] == "(site:facebook.com OR site:instagram.com) #PRF"
    assert client.delete(f"/api/hashtags/{hid}").status_code == 204


def test_hashtags_collect_e_track(client: TestClient, fake_fetcher) -> None:  # noqa: ANN001
    fake_fetcher.paginas["https://trends24.in/brazil/"] = (200, TRENDS_HTML)
    r = client.post("/api/hashtags/collect", json={"tag": "Eleicoes2026"}).json()
    assert r["ocorrencias_alvo"] == 2
    tags = {h["tag"]: h for h in client.get("/api/hashtags").json()}
    assert tags["#Eleicoes2026"]["contagem"] == 2 and "#PRF" in tags
    serie = client.get(f"/api/hashtags/{tags['#Eleicoes2026']['id']}/series").json()
    assert len(serie) == 1 and len(serie[0]["sha256"]) == 64

    h = client.post("/api/hashtags/track", json={"tag": "#PRF", "cron": "0 * * * *"}).json()
    assert h["monitor_id"]
    mon = client.get(f"/api/monitors/{h['monitor_id']}").json()
    assert mon["tipo"] == "hashtag"
    run = client.post(f"/api/monitors/{mon['id']}/run-now").json()
    assert run["status"] == "ok" and run["resultado"]["ocorrencias_alvo"] == 1


# ---------------------------------------------------------------- imagens
def test_images_upload_e_deeplinks(client: TestClient) -> None:
    r = client.post(
        "/api/images/upload",
        files={"arquivo": ("a.png", PNG, "image/png")},
        data={"origem_url": "https://ex.com/a.png"},
    ).json()
    assert r["evidencia"]["tipo"] == "imagem"
    assert r["provedores"]["tineye"]["por_url"].startswith("https://tineye.com/search?url=")
    assert r["provedores"]["sensity"]["abrir"] == "https://platform.sensity.ai/login"
    assert client.post("/api/images/upload", files={"arquivo": ("a.txt", b"x", "text/plain")}).status_code == 415
    assert client.get("/api/images/deeplinks", params={"url": "ftp://x"}).status_code == 422


# ---------------------------------------------------------------- settings
def test_settings_persistencia(client: TestClient, data_dir: Path) -> None:
    padrao = client.get("/api/settings").json()
    assert padrao["tipografia"]["fontSizeBase"] == 16
    padrao["tema"]["primary"] = "#FF0000"
    padrao["tipografia"]["fontSizeBase"] = 20
    r = client.put("/api/settings", json=padrao)
    assert r.json()["tema"]["primary"] == "#ff0000"
    assert json.loads((data_dir / "settings.json").read_text())["tipografia"]["fontSizeBase"] == 20
    padrao["tema"]["primary"] = "red"
    assert client.put("/api/settings", json=padrao).status_code == 422
    padrao["tema"]["primary"] = "#000000"
    padrao["tipografia"]["fontSizeBase"] = 30
    assert client.put("/api/settings", json=padrao).status_code == 422
    assert client.post("/api/settings/reset").json()["tipografia"]["fontSizeBase"] == 16
    assert "disponiveis" in client.get("/api/settings/browsers").json()


def test_monitor_delete_cascata_remove_execucoes(client: TestClient) -> None:
    from sqlmodel import Session, select

    from app import db
    from app.models.monitor import MonitorRun

    mid = client.post("/api/monitors", json={"nome": "c", "query": "PRF"}).json()["id"]
    client.post(f"/api/monitors/{mid}/run-now")
    client.post(f"/api/monitors/{mid}/run-now")
    assert client.delete(f"/api/monitors/{mid}").status_code == 204
    with Session(db.get_engine()) as s:
        assert s.exec(select(MonitorRun).where(MonitorRun.monitor_id == mid)).all() == []


def test_hashtags_variants_endpoint(client: TestClient) -> None:
    a = client.post("/api/hashtags", json={"tag": "#Eleições2026", "contagem": 5}).json()
    b = client.post("/api/hashtags", json={"tag": "#Eleicoes2026", "contagem": 2}).json()
    client.post("/api/hashtags", json={"tag": "#PRF"})
    assert a["chave_normalizada"] == b["chave_normalizada"] == "#eleicoes2026"
    for hid in (a["id"], b["id"]):  # vale nos dois sentidos
        r = client.get(f"/api/hashtags/{hid}/variants").json()
        assert [v["tag"] for v in r["variantes"]] == ["#Eleições2026", "#Eleicoes2026"]
    assert client.get("/api/hashtags/99999/variants").status_code == 404


def test_invites_scan_expoe_engines_sem_resposta(client: TestClient, fake_searxng) -> None:  # noqa: ANN001
    import httpx

    original = fake_searxng.handler

    def parcial(req: httpx.Request) -> httpx.Response:
        resp = original(req)
        if req.url.path == "/search":
            corpo = resp.json() | {"unresponsive_engines": [["duckduckgo", "CAPTCHA"]]}
            return httpx.Response(200, json=corpo)
        return resp

    from app.services import searxng_client

    searxng_client.set_searxng(searxng_client.SearxngClient(base_url="http://searxng.test", transport=httpx.MockTransport(parcial)))
    r = client.post("/api/invites/scan", json={"termo": "x", "plataformas": ["whatsapp"]}).json()
    assert r["execucoes"][0]["engines_sem_resposta"] == [["duckduckgo", "CAPTCHA"]]


def test_tools_checagem_de_fatos_e_busca_em_redes(client: TestClient) -> None:
    tools = client.get("/api/tools").json()
    por_cat: dict[str, set[str]] = {}
    for t in tools:
        por_cat.setdefault(t["categoria"], set()).add(t["url"])
    assert {
        "https://checamos.afp.com/",
        "https://projetocomprova.com.br/",
        "https://lupa.uol.com.br/",
        "https://www.aosfatos.org/",
        "https://g1.globo.com/fato-ou-fake/",
        "https://www.boatos.org/",
        "https://www.justicaeleitoral.jus.br/fato-ou-boato/",
        "https://toolbox.google.com/factcheck/explorer",
    } <= por_cat["Checagem de fatos"]
    assert {"https://x.com/explore", "https://www.tiktok.com/search", "https://www.instagram.com/explore/tags/"} <= por_cat["Busca em redes"]
    # as 16 ferramentas do documento mestre continuam presentes (contrato do hub)
    assert len([t for t in tools if t["categoria"] in {"Twitter - X", "Facebook", "Busca por Imagens", "Ferramentas"}]) == 16
    assert client.get("/api/tools", params={"categoria": "Checagem de fatos"}).json().__len__() == 9


def test_tools_deeplinks_novos(client: TestClient) -> None:
    r = client.get("/api/tools/deeplink", params={"tool": "x_search", "q": "PRF -is:retweet since:2026-10-04"}).json()
    assert r["url"] == "https://x.com/search?q=PRF+-is%3Aretweet+since%3A2026-10-04&src=typed_query&f=live" and r["prefill"]
    r = client.get("/api/tools/deeplink", params={"tool": "google_factcheck", "q": "PRF blitz"}).json()
    assert r["url"] == "https://toolbox.google.com/factcheck/explorer/search/PRF+blitz;hl=pt"
    r = client.get("/api/tools/deeplink", params={"tool": "instagram_tag", "q": "#Eleicoes 2026"}).json()
    assert r["url"] == "https://www.instagram.com/explore/tags/Eleicoes2026/"
    r = client.get("/api/tools/deeplink", params={"tool": "instagram_tag", "q": "#"}).json()
    assert r["url"] == "https://www.instagram.com/explore/tags/" and not r["prefill"]
    r = client.get("/api/tools/deeplink", params={"tool": "afp_checamos", "q": "x"}).json()
    assert r["url"] == "https://checamos.afp.com/" and not r["prefill"]
