from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------- perfis
def test_perfis_crud_deeplinks_e_monitor(client: TestClient) -> None:
    r = client.post("/api/perfis", json={"rede": "x", "handle": "https://x.com/PRFBrasil", "rotulo": "PRF Brasil", "categoria": "institucional"})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["handle"] == "PRFBrasil" and p["url"] == "https://x.com/PRFBrasil"
    assert client.post("/api/perfis", json={"rede": "x", "handle": "PRFBRASIL", "rotulo": "dup"}).status_code == 409  # caixa diferente = mesmo perfil
    assert client.post("/api/perfis", json={"rede": "x", "handle": "nome com espaço"}).status_code == 422
    assert client.post("/api/perfis", json={"rede": "site", "handle": "exemplo.org"}).status_code == 422
    assert client.post("/api/perfis", json={"rede": "instagram", "handle": "coletivo", "categoria": "coletivo"}).status_code == 201
    assert len(client.get("/api/perfis").json()) == 2
    assert len(client.get("/api/perfis", params={"rede": "x"}).json()) == 1

    dl = client.get(f"/api/perfis/{p['id']}/deeplinks").json()
    assert dl["perfil"] == "https://x.com/PRFBrasil"
    assert dl["query_mencoes_x"].startswith("(from:PRFBrasil OR @PRFBrasil) -is:retweet since:")
    assert dl["deeplinks_x"]["x"].startswith("https://x.com/search?q=") and "google" in dl["deeplinks"]

    mon = client.post(f"/api/perfis/{p['id']}/monitor", json={})
    assert mon.status_code == 201 and mon.json()["query"].startswith("(from:PRFBrasil")  # X por padrão para perfil do X
    assert client.get(f"/api/perfis/{p['id']}").json()["monitor_id"] == mon.json()["id"]

    assert client.patch(f"/api/perfis/{p['id']}", json={"ativo": False, "notas": "n"}).json()["ativo"] is False
    csv_txt = client.get("/api/perfis/export", params={"formato": "csv"}).text
    assert csv_txt.splitlines()[0].startswith("id,rede,handle,url")
    assert client.delete(f"/api/perfis/{p['id']}").status_code == 204
    assert client.get(f"/api/perfis/{p['id']}").status_code == 404


# ---------------------------------------------------------------- itens e boletim consolidado
def test_boletim_itens_e_consolidado(client: TestClient) -> None:
    ev = client.post("/api/evidence", files={"arquivo": ("print.txt", b"x", "text/plain")}).json()
    r = client.post("/api/boletim/itens", json={"data": "2026-10-03", "secao": "noticia", "titulo": "PRF promete livre deslocamento", "url": "https://ex.org/n", "fonte": "Metrópoles"})
    assert r.status_code == 201, r.text
    item = r.json()
    r = client.post("/api/boletim/itens", json={"data": "2026-10-03", "secao": "fake_news", "titulo": "É falso que…", "fonte": "AFP", "evidence_id": ev["id"]})
    assert r.status_code == 201
    assert client.post("/api/boletim/itens", json={"data": "2026-10-03", "secao": "fofoca", "titulo": "x"}).status_code == 422
    assert client.post("/api/boletim/itens", json={"data": "2026-10-03", "secao": "noticia", "titulo": "x", "url": "ex.org"}).status_code == 422
    assert client.post("/api/boletim/itens", json={"data": "2026-10-03", "secao": "noticia", "titulo": "x", "evidence_id": 9999}).status_code == 422
    assert len(client.get("/api/boletim/itens", params={"data": "2026-10-03"}).json()) == 2
    assert len(client.get("/api/boletim/itens", params={"secao": "fake_news"}).json()) == 1
    assert client.patch(f"/api/boletim/itens/{item['id']}", json={"resumo": "Resumo."}).json()["resumo"] == "Resumo."

    # agenda, perfil e hashtag entram no consolidado
    client.post("/api/agenda", json={"candidato": "Candidato A", "titulo": "Carreata", "tipo": "carreata", "data": "2026-10-03", "cidade": "Americana", "uf": "SP", "rodovias": ["BR-116"], "impacto_rodovia": True})
    client.post("/api/perfis", json={"rede": "x", "handle": "PRFBrasil", "rotulo": "PRF Brasil", "categoria": "institucional"})
    client.post("/api/hashtags", json={"tag": "#Eleicoes2026", "contagem": 4})

    b = client.get("/api/boletim/2026-10-03").json()
    assert b["titulo"] == "INFORMAÇÕES RELEVANTES - 03 OUT 2026 (sábado)"
    assert [i["titulo"] for i in b["secoes"]["noticia"]] == ["PRF promete livre deslocamento"]
    assert b["secoes"]["fake_news"][0]["evidence_id"] == ev["id"]
    assert b["agenda"]["total"] == 1 and b["agenda"]["com_impacto_rodovia"] == 1 and "Candidato A" in b["agenda"]["por_candidato"]
    assert b["perfis"][0]["handle"] == "PRFBrasil"
    assert b["hashtags"][0]["tag"] == "#Eleicoes2026"
    assert "## AGENDA DOS CANDIDATOS\n**Candidato A**\n- — — Carreata (carreata) — Americana/SP — BR-116 — PODERÁ IMPACTAR" in b["markdown"]

    md = client.get("/api/boletim/2026-10-03/export", params={"formato": "md"})
    assert md.headers["content-type"].startswith("text/markdown") and md.text.startswith("# INFORMAÇÕES RELEVANTES - 03 OUT 2026")
    html = client.get("/api/boletim/2026-10-03/export", params={"formato": "html"})
    assert html.headers["content-type"].startswith("text/html") and "<h2>FAKE NEWS</h2>" in html.text
    js = client.get("/api/boletim/2026-10-03/export", params={"formato": "json"}).json()
    assert js["agenda"][0]["rodovias"] == ["BR-116"] and js["hashtags"][0]["contagem"] == 4
    assert client.get("/api/boletim/2026-10-03/export", params={"formato": "pdf"}).status_code == 422

    # apagar a evidência não apaga o item (FK SET NULL)
    assert client.delete(f"/api/evidence/{ev['id']}").status_code == 204
    assert client.get("/api/boletim/itens", params={"secao": "fake_news"}).json()[0]["evidence_id"] is None
    assert client.delete(f"/api/boletim/itens/{item['id']}").status_code == 204
    assert client.delete(f"/api/boletim/itens/{item['id']}").status_code == 404


def test_boletim_dia_vazio(client: TestClient) -> None:
    b = client.get("/api/boletim/2026-10-04").json()
    assert b["secoes"] == {} and b["agenda"]["total"] == 0
    assert "## NOTÍCIAS RELEVANTES\n-\n" in b["markdown"]
