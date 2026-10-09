"""Do cartaz para a busca: termos extraídos do OCR → convites abertos, menções (SearXNG) e monitor contínuo."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.convocacoes import busca
from tests.conftest import FakeOpenClaw, FakeSearxng

pytestmark = pytest.mark.integration

OCR = """9 de outubro
• MG: ato “Estudantes contra Flávio Bolsonaro”, às 17h, na Praça Afonso
Arinos, em Belo Horizonte
•RS: FURG, às 18h
• MA: UEMA – São Luís, às 18h, no Auditório do CCSA
• PR: UEPG, às 19h
13 de outubro
• BA: Feira de Santana, às 16h, em frente ao Colégio Gastão
• RJ: UFRJ – Fundão, às 18h #AtoEstudantil @uneoficial"""


def test_extrair_termos_do_cartaz() -> None:
    tb = busca.extrair_termos(OCR)
    assert tb.frases == ["Estudantes contra Flávio Bolsonaro"]
    assert "Praça Afonso Arinos" in tb.locais and "Belo Horizonte" in tb.locais and "Auditório do CCSA" in tb.locais and "Colégio Gastão" in tb.locais
    assert {"FURG", "UEMA", "UEPG", "UFRJ", "CCSA"} <= set(tb.organizacoes)
    assert tb.hashtags == ["#AtoEstudantil"] and tb.mencoes == ["@uneoficial"]
    assert "9 de outubro" in tb.datas and "13 de outubro" in tb.datas
    assert tb.termos[0] == "Estudantes contra Flávio Bolsonaro" and len(tb.termos) <= busca.MAX_TERMOS
    assert tb.query_mencoes.startswith('("Estudantes contra Flávio Bolsonaro" OR "Praça Afonso Arinos"') and tb.query_mencoes.endswith("(ato OR manifestação OR protesto)")
    assert "google" in tb.deeplinks and "x" in tb.deeplinks
    assert busca.extrair_termos("").termos == [] and busca.extrair_termos("").query_mencoes == ""
    assert busca.montar_query_mencoes(["#tag"]) == "#tag (ato OR manifestação OR protesto)"


def _deteccao(client: TestClient) -> int:
    r = client.post("/api/convocacoes/analisar", data={"texto": OCR + "\nconcentração na BR-116", "salvar": "true"})
    assert r.status_code == 201
    return r.json()["deteccao"]["id"]


def test_busca_termos_convites_mencoes_e_monitor(client: TestClient, fake_searxng: FakeSearxng, fake_openclaw: FakeOpenClaw) -> None:
    det = _deteccao(client)
    tb = client.get(f"/api/convocacoes/{det}/busca").json()
    assert "Estudantes contra Flávio Bolsonaro" in tb["termos"] and tb["ia"] is False and tb["query_mencoes"]
    assert client.get("/api/convocacoes/999/busca").status_code == 404

    # IA enriquece (agent extrator)
    fake_openclaw.responder("extrator", {"termos": ["Praça Afonso Arinos BH", "UNE"], "hashtags": ["#ForaBolsonaro"], "observacoes": "ato estudantil nacional"})
    tbia = client.post(f"/api/convocacoes/{det}/busca/ia").json()
    assert tbia["ia"] is True and "UNE" in tbia["termos"] and "#ForaBolsonaro" in tbia["hashtags"] and tbia["observacoes"] == "ato estudantil nacional"
    assert fake_openclaw.chamadas[-1]["agent"] == "extrator" and "termos_busca" in fake_openclaw.chamadas[-1]["mensagem"]

    # convites: o SearXNG devolve um link de grupo nas consultas do termo
    for q in busca.extrair_termos(OCR).termos[:1]:
        from app.services.convites import montar_queries_searxng

        for plat, consultas in montar_queries_searxng(q).items():
            for c in consultas:
                fake_searxng.respostas[c] = [{"url": "https://exemplo.org/post", "title": "Grupo do ato", "content": "entra no grupo https://chat.whatsapp.com/ABCDEFGHIJK1234567890" if plat == "whatsapp" else "canal https://t.me/+abcdefghijk"}]
    r = client.post(f"/api/convocacoes/{det}/busca/convites", json={"termos": [busca.extrair_termos(OCR).termos[0]], "max_consultas": 1}).json()
    assert r["novos"] >= 1 and any(c["plataforma"].startswith("whatsapp") for c in r["convites"])
    assert any(i["termo"] == "Estudantes contra Flávio Bolsonaro" for i in client.get("/api/invites").json())
    assert "busca de convites" in client.get(f"/api/convocacoes/{det}").json()["notas"]

    # menções: resultados normalizados + deeplinks
    fake_searxng.respostas[tb["query_mencoes"]] = [{"url": "https://g1.test/ato", "title": "Ato reúne estudantes em BH", "content": "…", "engines": ["bing"], "publishedDate": "2026-10-09T10:00:00"}]
    m = client.post(f"/api/convocacoes/{det}/busca/mencoes", json={"query": tb["query_mencoes"]}).json()
    assert m["erro"] is None and m["resultados"][0]["titulo"] == "Ato reúne estudantes em BH" and m["resultados"][0]["publicado_em"].startswith("2026-10-09") and "google" in m["deeplinks"]

    # monitor contínuo com os termos (entra no Radar e na IA)
    mon = client.post(f"/api/convocacoes/{det}/monitor", json={"query": tb["query_mencoes"]})
    assert mon.status_code == 201 and mon.json()["ia"] is True and mon.json()["canal_alerta"] == "nenhum" and mon.json()["nome"].startswith("Convocação #")
    assert any(m2["id"] == mon.json()["id"] for m2 in client.get("/api/monitors").json())
    assert f"monitor #{mon.json()['id']}" in client.get(f"/api/convocacoes/{det}").json()["notas"]
    assert client.post(f"/api/convocacoes/{det}/busca/convites", json={"termos": []}).status_code == 422
