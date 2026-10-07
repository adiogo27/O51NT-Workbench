from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.unit.test_convites_v2 import TG_GRUPO, TG_INVALIDO, WA_OK, WA_REVOGADO
from tests.unit.test_radar_service import RSS

pytestmark = pytest.mark.integration


def test_radar_grava_alerta_na_inbox(client: TestClient, fake_fetcher) -> None:  # noqa: ANN001
    fake_fetcher.paginas["https://feeds.test/a.xml"] = (200, RSS)
    for f in client.get("/api/radar/fontes").json():
        client.patch(f"/api/radar/fontes/{f['id']}", json={"ativa": False})
    client.post("/api/radar/fontes", json={"nome": "A", "url": "https://feeds.test/a.xml"})
    m = client.post("/api/monitors", json={"nome": "blitz", "query": "PRF blitz"}).json()
    r = client.post("/api/radar/ciclo").json()
    assert r["alertas"] == 1
    al = client.get("/api/alertas", params={"tipo": "radar"}).json()
    assert len(al) == 1 and al[0]["monitor_id"] == m["id"] and al[0]["severidade"] == "media" and "blitz" in al[0]["titulo"]
    assert client.get("/api/alertas/contagem").json()["radar"] == 1
    assert client.patch(f"/api/alertas/{al[0]['id']}", json={"lido": True}).json()["lido"] is True
    assert client.get("/api/alertas/contagem").json()["total"] == 0
    assert client.post("/api/alertas/marcar-todos").json() == {"marcados": 0}
    assert client.delete(f"/api/alertas/{al[0]['id']}").status_code == 204
    assert client.get("/api/alertas").json() == [] and client.patch("/api/alertas/999", json={"lido": True}).status_code == 404


def test_invites_queries_extrair_registrar(client: TestClient) -> None:
    q = client.get("/api/invites/queries", params={"termo": "movimento brasil"}).json()
    assert "queries_searxng" in q and len(q["queries_searxng"]["whatsapp"]) == 5 and q["queries"]["whatsapp"].startswith("(site:")
    e = client.post("/api/invites/extrair", json={"texto": "GRUPOS: chat.whatsapp.com/GM4b5kGzIFm36GoyM7AOlM Movimento.pelobr chat.whatsapp.com/GalZzza5qmdGz7dqj3tBv2 Telegram t.me/+C7JN-YpjIacxNTQx"}).json()
    assert [c["plataforma"] for c in e["convites"]] == ["whatsapp", "whatsapp", "telegram"] and e["registrados"] == []
    e2 = client.post("/api/invites/extrair", json={"texto": "t.me/+C7JN-YpjIacxNTQx", "registrar": True, "termo": "manual", "fonte_url": "https://x.com/p/1"}).json()
    assert len(e2["registrados"]) == 1 and e2["registrados"][0]["fonte_url"] == "https://x.com/p/1"
    r = client.post("/api/invites/registrar", json={"url": "https://chat.whatsapp.com/GM4b5kGzIFm36GoyM7AOlM", "termo": "colado"})
    assert r.status_code == 201 and r.json()["plataforma"] == "whatsapp" and r.json()["status"] == "desconhecido"
    assert client.post("/api/invites/registrar", json={"url": "https://exemplo.com/nada"}).status_code == 422
    assert len(client.get("/api/invites", params={"plataforma": "whatsapp"}).json()) == 1
    assert len(client.get("/api/invites", params={"status": "desconhecido"}).json()) == 2


def test_invites_testar_ativo_revogado_robots(client: TestClient, fake_fetcher) -> None:  # noqa: ANN001
    wa = client.post("/api/invites/registrar", json={"url": "https://chat.whatsapp.com/GM4b5kGzIFm36GoyM7AOlM", "termo": "movimento brasil"}).json()
    wa2 = client.post("/api/invites/registrar", json={"url": "https://chat.whatsapp.com/GalZzza5qmdGz7dqj3tBv2"}).json()
    tg = client.post("/api/invites/registrar", json={"url": "https://t.me/+C7JN-YpjIacxNTQx"}).json()
    tg2 = client.post("/api/invites/registrar", json={"url": "https://t.me/+expirado12345"}).json()
    fake_fetcher.paginas[wa["url"]] = (200, WA_OK)
    fake_fetcher.binarios["https://pps.whatsapp.net/v/t61/foto.jpg"] = (200, b"\xff\xd8\xff" + b"0" * 50, "image/jpeg")
    fake_fetcher.paginas[wa2["url"]] = (200, WA_REVOGADO)
    fake_fetcher.paginas[tg["url"]] = (200, TG_GRUPO)
    fake_fetcher.binarios["https://cdn4.telesco.pe/file/x.jpg"] = (200, b"\xff\xd8\xff" + b"1" * 50, "image/jpeg")
    fake_fetcher.paginas[tg2["url"]] = (200, TG_INVALIDO)

    r = client.post(f"/api/invites/{wa['id']}/testar").json()
    assert r["verificacao"]["status"] == "ativo" and r["convite"]["nome_grupo"] == "MOVIMENTO BRASIL 🇧🇷" and r["convite"]["membros"] is None
    assert r["convite"]["evidencia_id"] and r["convite"]["verificado_em"] and r["convite"]["http_status"] == 200 and r["convite"]["score_relevantia" if False else "score_relevancia"] >= 0
    ev = client.get(f"/api/evidence/{r['convite']['evidencia_id']}").json()
    assert ev["origem_url"] == wa["url"] and ev["tipo"] == "imagem"
    assert client.post(f"/api/invites/{wa2['id']}/testar").json()["convite"]["status"] == "revogado"
    t = client.post(f"/api/invites/{tg['id']}/testar").json()
    assert t["convite"]["status"] == "ativo" and t["convite"]["membros"] == 1234 and t["convite"]["nome_grupo"].startswith("Grupo do Telegram") and t["convite"]["score_relevancia"] >= 30
    assert client.post(f"/api/invites/{tg2['id']}/testar").json()["convite"]["status"] == "revogado"
    assert client.post("/api/invites/999/testar").status_code == 404
    # listagem por status + export com colunas novas
    assert {i["url"] for i in client.get("/api/invites", params={"status": "ativo"}).json()} == {wa["url"], tg["url"]}
    csv_txt = client.get("/api/invites/export", params={"formato": "csv"}).text
    assert "nome_grupo" in csv_txt.splitlines()[0] and "MOVIMENTO BRASIL" in csv_txt
    # testar-todos roda em background (BackgroundTasks executa antes da resposta no TestClient)
    r_all = client.post("/api/invites/testar-todos", json={"ids": [wa2["id"], tg2["id"]]}).json()
    assert r_all == {"agendados": 2}
    assert client.post("/api/invites/testar-todos", json={"ids": [999]}).json() == {"agendados": 0}


def test_invites_testar_respeita_robots_com_toggle(client: TestClient, fake_fetcher) -> None:  # noqa: ANN001
    """Cliente novo = cache de robots.txt novo: o Disallow precisa estar lá antes do 1º acesso ao domínio."""
    fake_fetcher.paginas["https://t.me/robots.txt"] = (200, "User-agent: *\nDisallow: /\n")
    bloq = client.post("/api/invites/registrar", json={"url": "https://t.me/joinchat/BLOQUEADO123"}).json()
    fake_fetcher.paginas[bloq["url"]] = (200, TG_GRUPO)
    rb = client.post(f"/api/invites/{bloq['id']}/testar").json()
    assert rb["verificacao"]["status"] == "desconhecido" and rb["verificacao"]["robots_permite"] is False and "robots" in rb["convite"]["erro_verificacao"]
    rb2 = client.post(f"/api/invites/{bloq['id']}/testar", params={"ignorar_robots": "true"}).json()
    assert rb2["verificacao"]["status"] == "ativo" and rb2["verificacao"]["robots_permite"] is False and rb2["convite"]["membros"] == 1234
