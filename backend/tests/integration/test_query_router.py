from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_templates_seedados(client: TestClient) -> None:
    tpls = client.get("/api/query/templates").json()
    assert len(tpls) >= 10
    nomes = {t["nome"] for t in tpls}
    assert {"Redes sociais após data", "Localidade após data", "Convites WhatsApp", "Convites Telegram"} <= nomes
    assert all(t["origem_pdf"] for t in tpls)


def test_compose_blocos(client: TestClient) -> None:
    r = client.post(
        "/api/query/compose",
        json={
            "precisao": {"grupos_or": [["PRF", "Polícia Rodoviária"]], "excluir": ["concurso"]},
            "temporal": {"after": "2026-10-01"},
            "escopo": {"sites": ["uol.com.br"]},
        },
    ).json()
    assert r["query"] == 'site:uol.com.br (PRF OR "Polícia Rodoviária") -concurso after:2026-10-01'
    assert r["valida"]
    assert set(r["deeplinks"]) == {"google", "bing", "duckduckgo", "startpage"}
    assert "after" in r["compatibilidade"]["bing"]


def test_compose_com_template(client: TestClient) -> None:
    tpl = next(t for t in client.get("/api/query/templates").json() if t["nome"] == "Convites Telegram")
    r = client.post(
        "/api/query/compose", json={"template_id": tpl["id"], "valores_template": {"Termo a ser pesquisado": "blitz"}}
    ).json()
    assert r["query"].endswith('(t.me/joinchat "blitz")')


def test_compose_template_inexistente(client: TestClient) -> None:
    assert client.post("/api/query/compose", json={"template_id": 9999}).status_code == 404


def test_compose_janela_invalida(client: TestClient) -> None:
    r = client.post("/api/query/compose", json={"precisao": {"termos": ["PRF"]}, "temporal": {"after": "2026-10-10", "before": "2026-10-01"}}).json()
    assert not r["valida"]
    assert r["erros"][0]["codigo"] == "janela_temporal_vazia"


def test_validate(client: TestClient) -> None:
    r = client.post("/api/query/validate", json={"query": '("Termo * Termo2)'}).json()
    assert not r["valida"]
    r = client.post("/api/query/validate", json={"query": "PRF site:gov.br -site:gov.br"}).json()
    assert {e["codigo"] for e in r["erros"]} == {"site_conflitante"}


def test_crud_template(client: TestClient) -> None:
    r = client.post("/api/query/templates", json={"nome": "Meu", "query": "PRF after:2026-01-01", "placeholders": ["PRF"]})
    assert r.status_code == 201
    tid = r.json()["id"]
    assert r.json()["placeholders"] == ["PRF"]
    assert client.post("/api/query/templates", json={"nome": "Meu", "query": "x"}).status_code == 409
    assert client.delete(f"/api/query/templates/{tid}").status_code == 204
    assert client.delete(f"/api/query/templates/{tid}").status_code == 404


def test_historico(client: TestClient) -> None:
    for q in ("a", "b"):
        assert client.post("/api/query/history", json={"query": q, "motor": "bing"}).status_code == 201
    h = client.get("/api/query/history").json()
    assert [x["query"] for x in h] == ["b", "a"]
    assert client.delete("/api/query/history").json() == {"removidas": 2}
    assert client.get("/api/query/history").json() == []


def test_historico_poda_por_teto_e_idade(client: TestClient) -> None:
    for i in range(5):
        client.post("/api/query/history", json={"query": f"q{i}"})
    assert client.delete("/api/query/history", params={"max_entries": 2}).json() == {"removidas": 3}
    assert [x["query"] for x in client.get("/api/query/history").json()] == ["q4", "q3"]
    assert client.delete("/api/query/history", params={"older_than_days": 90}).json() == {"removidas": 0}
    assert client.delete("/api/query/history", params={"older_than_days": 0}).status_code == 422


def test_historico_respeita_politica_dos_settings(client: TestClient) -> None:
    cfg = client.get("/api/settings").json()
    cfg["preferencias"]["historicoMaxEntradas"] = 3
    client.put("/api/settings", json=cfg)
    for i in range(6):
        client.post("/api/query/history", json={"query": f"q{i}"})
    assert len(client.get("/api/query/history").json()) == 3


def test_scrape_query_via_searxng(client: TestClient, fake_searxng) -> None:  # noqa: ANN001
    fake_searxng.respostas["PRF blitz"] = [{"url": "https://g1.globo.com/a", "title": "A", "content": "..."}]
    r = client.post("/api/query/scrape", json={"query": "PRF blitz", "engines": ["duckduckgo", "startpage"]}).json()
    ex = r["execucoes"][0]
    assert ex["resultados"] == [{"titulo": "A", "url": "https://g1.globo.com/a"}]
    assert len(ex["sha256"]) == 64 and ex["fonte"] == "searxng:duckduckgo,startpage"
    assert fake_searxng.consultas[-1]["engines"] == "duckduckgo,startpage"


def test_scrape_query_searxng_indisponivel_503(client: TestClient) -> None:
    import httpx

    from app.services import searxng_client

    def recusa(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=req)

    searxng_client.set_searxng(searxng_client.SearxngClient(base_url="http://off", transport=httpx.MockTransport(recusa)))
    r = client.post("/api/query/scrape", json={"query": "PRF"})
    assert r.status_code == 503 and "SearXNG" in r.json()["detail"]
    assert client.get("/api/searxng/status").json()["disponivel"] is False


def test_scrape_query_invalida(client: TestClient) -> None:
    r = client.post("/api/query/scrape", json={"query": '"aberta'}).json()
    assert r["erro"] == "query inválida"


def test_locations(client: TestClient) -> None:
    r = client.get("/api/locations", params={"q": "br-116"}).json()
    assert r[0]["termo"] == '(BR-116 OR "BR 116" OR BR116)'
