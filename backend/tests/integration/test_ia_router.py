"""Pipeline do assistente de IA de ponta a ponta: Radar → fila → agents (simulados) → alertas/Telegram → aprovação → Boletim/Agenda."""

from __future__ import annotations

from typing import Any

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from app import config
from tests.conftest import FakeFetcher, FakeOpenClaw

pytestmark = pytest.mark.integration

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Portal</title>
<item><title>PRF faz blitz na BR-116 e apreende carga em Curitiba</title><link>https://portal.test/blitz-br-116</link><description>Operação da PRF na BR-116.</description><pubDate>Fri, 09 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>Carreata convoca ato de domingo com bloqueio da BR-101</title><link>https://portal.test/carreata-br-101</link><description>Organizadores pedem concentração às 9h no trevo da BR-101 em Palhoça.</description><pubDate>Fri, 09 Oct 2026 11:00:00 GMT</pubDate></item>
<item><title>Receita de bolo de fubá</title><link>https://portal.test/bolo</link><description>Nada a ver.</description></item>
</channel></rss>"""

TRIAGEM_RELEVANTE = {"veredito": "RELEVANTE", "severidade": "alta", "justificativa": "Convocação com data, local e rodovia federal.", "acao_sugerida": "monitorar BR-101 no domingo", "secao": "manifestacao", "eh_evento": True, "tags": ["carreata", "BR-101"]}
EVENTO = {"tipo": "carreata", "titulo": "Carreata de domingo", "data": "2026-10-12", "hora": "09:00", "cidade": "Palhoça", "uf": "SC", "local": "trevo da BR-101", "rodovias": ["BR-101"], "organizador": "Coletivo X", "pauta": "protesto", "canais": ["whatsapp"], "impacto_rodovia_federal": True, "confianca": 0.9, "_notas": ""}
PESQUISA = {"resposta": "Convocação confirmada em dois veículos.", "verificacao": "confirmado", "fontes": [{"url": "https://oficial.test/nota", "titulo": "Nota", "trecho": "..."}], "confianca": 0.8, "lacunas": "sem estimativa de público"}
CARTAO = {"titulo": "Carreata deve bloquear a BR-101 em Palhoça no domingo", "resumo": "Organizadores convocam concentração às 9h no trevo da BR-101.", "impacto_rodovia": "Bloqueio parcial da BR-101 km 210.", "acao": "Acionar o plantão regional.", "fontes": ["https://portal.test/carreata-br-101", "https://oficial.test/nota"]}


def _preparar(client: TestClient, fake_fetcher: FakeFetcher, prefs: dict[str, Any] | None = None, query: str = "BR-116 OR BR-101") -> int:
    for f in client.get("/api/radar/fontes").json():  # desliga as fontes seedadas (sem rede nos testes)
        client.patch(f"/api/radar/fontes/{f['id']}", json={"ativa": False})
    fake_fetcher.paginas["https://feeds.test/portal.xml"] = (200, RSS)
    assert client.post("/api/radar/fontes", json={"nome": "Portal", "url": "https://feeds.test/portal.xml"}).status_code == 201
    cfg = client.get("/api/settings").json()
    cfg["preferencias"].update({"iaAtivo": True, "iaBoletim": "aprovar", "iaAgenda": "aprovar", "iaPesquisarSeveridadeMin": "alta", **(prefs or {})})
    assert client.put("/api/settings", json=cfg).status_code == 200
    r = client.post("/api/monitors", json={"nome": "rodovias", "query": query, "canal_alerta": "jsonl"})
    assert r.status_code == 201 and r.json()["ia"] is True
    return r.json()["id"]


def test_fila_desligada_por_padrao(client: TestClient, fake_fetcher: FakeFetcher) -> None:
    for f in client.get("/api/radar/fontes").json():
        client.patch(f"/api/radar/fontes/{f['id']}", json={"ativa": False})
    fake_fetcher.paginas["https://feeds.test/portal.xml"] = (200, RSS)
    client.post("/api/radar/fontes", json={"nome": "Portal", "url": "https://feeds.test/portal.xml"})
    client.post("/api/monitors", json={"nome": "m", "query": "BR-116"})
    r = client.post("/api/radar/ciclo").json()
    assert r["hits_novos"] == 1 and r["alertas"] == 1  # alerta bruto preservado quando a IA está desligada
    assert client.get("/api/ia/tarefas").json() == []
    st = client.get("/api/ia/status").json()
    assert st["ativo"] is False and st["fila"]["pendente"] == 0 and st["openclaw_configurado"] is True


def test_pipeline_completo_relevante_com_aprovacao(client: TestClient, fake_fetcher: FakeFetcher, fake_openclaw: FakeOpenClaw, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "371824016")
    config.get_settings.cache_clear()
    _preparar(client, fake_fetcher, query="BR-101")
    fake_openclaw.responder("sentinela", TRIAGEM_RELEVANTE)
    fake_openclaw.responder("extrator", EVENTO)
    fake_openclaw.responder("pesquisador", PESQUISA)
    fake_openclaw.responder("redator", CARTAO)
    try:
        with respx.mock(base_url="https://api.telegram.org") as mock:
            envio = mock.post("/bot123:ABC/sendMessage").mock(return_value=Response(200, json={"ok": True, "result": {"message_id": 9}}))
            ciclo = client.post("/api/radar/ciclo").json()
            assert ciclo["hits_novos"] == 1 and ciclo["alertas"] == 0  # alerta bruto suprimido (iaSuprimirAlertasBrutos)
            fila = client.get("/api/ia/tarefas?status=pendente").json()
            assert len(fila) == 1 and fila[0]["url"] == "https://portal.test/carreata-br-101" and fila[0]["monitor_nome"] == "rodovias"
            res = client.post("/api/ia/ciclo", json={}).json()
            assert res["processadas"] == 1 and res["concluidas"] == 1 and res["motivo_parada"] is None
            t = client.get(f"/api/ia/tarefas/{fila[0]['id']}").json()
            assert t["status"] == "concluida" and t["veredito"] == "RELEVANTE" and t["severidade"] == "alta" and t["eh_evento"] is True
            assert t["evento"]["data"] == "2026-10-12" and t["pesquisa"]["verificacao"] == "confirmado" and t["cartao"]["titulo"].startswith("Carreata")
            assert t["aprovacao"] == "pendente" and t["alerta_id"] and t["telegram_enviado"] is True
            assert t["tokens_entrada"] == 4000 and t["custo_usd"] > 0 and "triagem=claude-haiku-5-5" in t["modelos"]
            assert [c["agent"] for c in fake_openclaw.chamadas] == ["sentinela", "extrator", "pesquisador", "redator"]
            assert fake_openclaw.chamadas[0]["modelo"] == "anthropic/claude-haiku-5-5" and fake_openclaw.chamadas[0]["auth"] == "Bearer token-teste"
            assert "<conteudo>" in fake_openclaw.chamadas[0]["mensagem"] and "BR-101" in fake_openclaw.chamadas[0]["mensagem"]
            assert envio.call_count == 1 and "aprovar " in envio.calls[0].request.content.decode()
            # inbox: alerta tipo "ia"; contagem mantém o contrato (sem chave nova) e inclui o total
            alertas = client.get("/api/alertas?tipo=ia").json()
            assert len(alertas) == 1 and alertas[0]["severidade"] == "alta" and alertas[0]["titulo"].startswith("[RELEVANTE]")
            cont = client.get("/api/alertas/contagem").json()
            assert set(cont) == {"total", "criticos", "convocacao", "convite", "radar"} and cont["total"] == 1
            st = client.get("/api/ia/status").json()
            assert st["aprovacoes_pendentes"] == 1 and st["alertas_ia_nao_lidos"] == 1 and st["custo_hoje"]["chamadas"] == 4
            # aprovação → Boletim + Agenda (idempotente)
            ap = client.post(f"/api/ia/tarefas/{t['id']}/aprovar", json={"destino": "ambos"}).json()
            assert ap["aprovacao"] == "aprovada" and ap["boletim_item_id"] and ap["agenda_evento_id"]
            ap2 = client.post(f"/api/ia/tarefas/{t['id']}/aprovar", json={"destino": "ambos"}).json()
            assert ap2["boletim_item_id"] == ap["boletim_item_id"] and ap2["agenda_evento_id"] == ap["agenda_evento_id"]
            itens = client.get("/api/boletim/itens").json()
            assert len(itens) == 1 and itens[0]["secao"] == "manifestacao" and "Fontes:" in itens[0]["resumo"] and itens[0]["url"] == "https://portal.test/carreata-br-101"
            ev = client.get("/api/agenda").json()
            assert len(ev) == 1 and ev[0]["rodovias"] == ["BR-101"] and ev[0]["impacto_rodovia"] is True and ev[0]["data"] == "2026-10-12" and ev[0]["uf"] == "SC" and ev[0]["tipo"] == "carreata"
            hit = client.get("/api/radar/hits?lidos=true").json()
            assert hit and hit[0]["boletim_item_id"] == ap["boletim_item_id"]
            assert client.get("/api/alertas?tipo=ia&lidos=false").json() == []  # aprovado = lido
    finally:
        config.get_settings.cache_clear()


def test_descartar_marca_lido_sem_alerta_e_uma_chamada(client: TestClient, fake_fetcher: FakeFetcher, fake_openclaw: FakeOpenClaw) -> None:
    _preparar(client, fake_fetcher, query="BR-116")
    fake_openclaw.responder("sentinela", {"veredito": "DESCARTAR", "severidade": "baixa", "justificativa": "homônimo"})
    client.post("/api/radar/ciclo")
    res = client.post("/api/ia/ciclo").json()
    assert res["concluidas"] == 1 and len(fake_openclaw.chamadas) == 1
    t = client.get("/api/ia/tarefas").json()[0]
    assert t["veredito"] == "DESCARTAR" and t["alerta_id"] is None and t["aprovacao"] == "nao_se_aplica"
    assert client.get("/api/alertas").json() == [] and client.get("/api/radar/hits?lidos=false").json() == []


def test_observar_vai_para_o_resumo_periodico(client: TestClient, fake_fetcher: FakeFetcher, fake_openclaw: FakeOpenClaw, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    config.get_settings.cache_clear()
    _preparar(client, fake_fetcher, query="BR-116")
    fake_openclaw.responder("sentinela", {"veredito": "OBSERVAR", "severidade": "media", "justificativa": "operação de rotina", "secao": "noticia"})
    fake_openclaw.responder("redator", {"titulo": "Blitz na BR-116", "resumo": "Rotina.", "fontes": []})
    try:
        with respx.mock(base_url="https://api.telegram.org") as mock:
            envio = mock.post("/bot123:ABC/sendMessage").mock(return_value=Response(200, json={"ok": True, "result": {"message_id": 1}}))
            client.post("/api/radar/ciclo")
            client.post("/api/ia/ciclo")
            assert envio.call_count == 0  # OBSERVAR não vai na hora
            t = client.get("/api/ia/tarefas").json()[0]
            assert t["veredito"] == "OBSERVAR" and t["aprovacao"] == "nao_se_aplica" and [c["agent"] for c in fake_openclaw.chamadas] == ["sentinela", "redator"]
            assert client.get("/api/alertas?tipo=ia").json()[0]["severidade"] == "baixa"
            r = client.post("/api/ia/resumo").json()
            assert r["enviados"] == 1 and envio.call_count == 1 and "para observar" in envio.calls[0].request.content.decode()
            assert client.post("/api/ia/resumo").json()["enviados"] == 0  # já resumido
    finally:
        config.get_settings.cache_clear()


def test_teto_diario_e_gateway_indisponivel(client: TestClient, fake_fetcher: FakeFetcher, fake_openclaw: FakeOpenClaw) -> None:
    _preparar(client, fake_fetcher, {"iaCustoDiarioUsd": 0.0005}, query="BR-116 OR BR-101")
    fake_openclaw.responder("sentinela", {"veredito": "DESCARTAR", "severidade": "baixa", "justificativa": "x"})
    client.post("/api/radar/ciclo")
    assert len(client.get("/api/ia/tarefas?status=pendente").json()) == 2
    res = client.post("/api/ia/ciclo").json()
    assert res["processadas"] == 1 and "teto" in res["motivo_parada"]  # 1ª custa ~0.0015 > teto → a 2ª espera
    assert client.get("/api/ia/status").json()["custo_hoje"]["bloqueado"] is True
    # gateway fora do ar: nada é consumido, a tarefa fica pendente sem contar tentativa
    cfg = client.get("/api/settings").json()
    cfg["preferencias"]["iaCustoDiarioUsd"] = 10
    client.put("/api/settings", json=cfg)
    fake_openclaw.alcancavel = False
    res = client.post("/api/ia/ciclo").json()
    assert res["processadas"] == 0 and "indispon" in res["motivo_parada"]
    t = client.get("/api/ia/tarefas?status=pendente").json()
    assert len(t) == 1 and t[0]["tentativas"] == 0
    assert client.get("/api/ia/saude").json()["alcancavel"] is False


def test_resposta_invalida_retenta_e_depois_erro(client: TestClient, fake_fetcher: FakeFetcher, fake_openclaw: FakeOpenClaw) -> None:
    _preparar(client, fake_fetcher, query="BR-116")
    fake_openclaw.responder("sentinela", "não consigo responder em JSON", "ainda sem JSON")
    client.post("/api/radar/ciclo")
    for esperado in ("pendente", "pendente", "erro"):
        client.post("/api/ia/ciclo")
        t = client.get("/api/ia/tarefas").json()[0]
        assert t["status"] == esperado and "sentinela" in t["erro"]
    assert len(fake_openclaw.chamadas) == 6  # 2 tentativas por ciclo × 3 ciclos
    # reprocessar zera e volta à fila; resposta válida conclui
    fake_openclaw.respostas["sentinela"] = [{"veredito": "DESCARTAR", "severidade": "baixa", "justificativa": "ok"}]
    assert client.post(f"/api/ia/tarefas/{t['id']}/reprocessar", json={"desde": "triagem"}).json()["status"] == "pendente"
    client.post("/api/ia/ciclo")
    assert client.get(f"/api/ia/tarefas/{t['id']}").json()["status"] == "concluida"


def test_override_de_modelo_recusado_cai_para_o_modelo_do_agent(client: TestClient, fake_fetcher: FakeFetcher, fake_openclaw: FakeOpenClaw) -> None:
    _preparar(client, fake_fetcher, query="BR-116")
    fake_openclaw.recusar_override = True
    fake_openclaw.responder("sentinela", {"veredito": "DESCARTAR", "severidade": "baixa", "justificativa": "x"})
    client.post("/api/radar/ciclo")
    assert client.post("/api/ia/ciclo").json()["concluidas"] == 1
    assert [c["modelo"] for c in fake_openclaw.chamadas] == [None]  # a recusa não é contabilizada; a 2ª chamada vai sem override
    assert client.get("/api/ia/tarefas").json()[0]["status"] == "concluida"


def test_monitor_sem_ia_e_tarefa_manual_e_acao_local(client: TestClient, fake_fetcher: FakeFetcher, fake_openclaw: FakeOpenClaw) -> None:
    mid = _preparar(client, fake_fetcher, query="BR-116")
    assert client.patch(f"/api/monitors/{mid}", json={"ia": False}).json()["ia"] is False
    client.post("/api/radar/ciclo")
    assert client.get("/api/ia/tarefas").json() == []  # monitor fora da IA não enfileira
    r = client.post("/api/ia/tarefas", json={"url": "https://portal.test/manual?utm_source=x", "titulo": "Manual"})
    assert r.status_code == 201 and r.json()["origem"] == "manual" and r.json()["url"] == "https://portal.test/manual"
    assert client.post("/api/ia/tarefas", json={"url": "https://portal.test/manual"}).status_code == 409
    assert client.post("/api/ia/tarefas", json={"url": "ftp://x"}).status_code == 422
    # ação por GET só de processos locais (TestClient não é loopback direto)
    assert client.get(f"/api/ia/tarefas/{r.json()['id']}/acao?acao=aprovar").status_code == 405
    assert client.post(f"/api/ia/tarefas/{r.json()['id']}/aprovar", json={}).status_code == 409  # ainda sem veredito
    assert client.post(f"/api/ia/tarefas/{r.json()['id']}/rejeitar", json={"motivo": "teste"}).json()["aprovacao"] == "rejeitada"
    assert client.delete(f"/api/ia/tarefas/{r.json()['id']}").status_code == 204


def test_deteccao_de_convocacao_entra_na_fila(client: TestClient, fake_openclaw: FakeOpenClaw) -> None:
    cfg = client.get("/api/settings").json()
    cfg["preferencias"].update({"iaAtivo": True, "convocacoesCanalAlerta": "nenhum"})
    client.put("/api/settings", json=cfg)
    texto = "GRANDE ATO NACIONAL domingo 12/10 9h concentração BR-116 km 20 todos convocados"
    r = client.post("/api/convocacoes/analisar", data={"texto": texto, "salvar": "true"})
    assert r.status_code == 201 and r.json()["alerta_id"]
    fila = client.get("/api/ia/tarefas?origem=deteccao").json()
    assert len(fila) == 1 and fila[0]["deteccao_id"] == r.json()["deteccao"]["id"] and "BR-116" in fila[0]["resumo"]
    fake_openclaw.responder("sentinela", {"veredito": "RELEVANTE", "severidade": "critica", "justificativa": "ato com rodovia", "eh_evento": True, "secao": "manifestacao"})
    fake_openclaw.responder("extrator", {**EVENTO, "rodovias": ["BR-116"], "uf": "PR", "cidade": "Curitiba"})
    fake_openclaw.responder("pesquisador", PESQUISA)
    fake_openclaw.responder("redator", CARTAO)
    client.post("/api/ia/ciclo")
    t = client.get(f"/api/ia/tarefas/{fila[0]['id']}").json()
    assert t["status"] == "concluida" and t["aprovacao"] == "pendente" and "<conteudo>" in fake_openclaw.chamadas[0]["mensagem"] and "detector de convocações" in fake_openclaw.chamadas[0]["mensagem"]


def test_fonte_pagina_html(client: TestClient, fake_fetcher: FakeFetcher) -> None:
    for f in client.get("/api/radar/fontes").json():
        client.patch(f"/api/radar/fontes/{f['id']}", json={"ativa": False})
    html = "<html><body><nav><a href='/politica'>Política e tudo mais do dia de hoje</a></nav><main>" + "".join(f"<a href='/noticia/{i}/prf-operacao-br-116-{i}'>PRF faz operação na BR-116 e apreende carga número {i}</a>" for i in range(3)) + "</main></body></html>"
    fake_fetcher.paginas["https://portal.test/ultimas"] = (200, html)
    teste = client.post("/api/radar/fontes/testar", json={"url": "https://portal.test/ultimas"}).json()
    assert teste["ok"] is True and teste["tipo_detectado"] == "pagina" and teste["itens"] == 3
    r = client.post("/api/radar/fontes", json={"nome": "Portal (página)", "url": "https://portal.test/ultimas", "tipo": "pagina", "intervalo_min": 60})
    assert r.status_code == 201 and r.json()["tipo"] == "pagina" and r.json()["intervalo_min"] == 60
    client.post("/api/monitors", json={"nome": "m", "query": "BR-116"})
    c1 = client.post("/api/radar/ciclo").json()
    assert c1["itens_novos"] == 3 and c1["hits_novos"] == 3
    c2 = client.post("/api/radar/ciclo").json()
    assert c2["fontes"] == [] and c2["itens_novos"] == 0  # intervalo próprio ainda não venceu
    f = client.get("/api/radar/fontes").json()[0]
    assert f["itens_total"] == 3 and f["ultima_mudanca"] is not None
    assert client.post("/api/radar/fontes", json={"nome": "x", "url": "https://portal.test/u2", "tipo": "pagina", "intervalo_min": 0}).status_code == 422


def test_ferramentas_router(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import ferramentas as svc

    cat = client.get("/api/ferramentas").json()
    assert cat["sensiveis_ativas"] is False and len(cat["ferramentas"]) >= 12
    monkeypatch.setitem(svc.REGISTRO, "eco", svc.Ferramenta("eco", "eco", "echo", "teste", "usuario", ["{alvo}"], "infra", 5, exemplo="x"))
    monkeypatch.setitem(svc.REGISTRO, "ausente", svc.Ferramenta("ausente", "ausente", "binario-inexistente-xyz", "teste", "dominio", ["{alvo}"], "infra", 5))
    r = client.post("/api/ferramentas/executar", json={"ferramenta": "eco", "alvo": "@PRFBrasil"}).json()
    assert r["ok"] is True and r["saida"].strip() == "PRFBrasil" and r["comando"][0] == "echo" and r["codigo"] == 0
    assert client.post("/api/ferramentas/executar", json={"ferramenta": "eco", "alvo": "a b"}).status_code == 422
    assert client.post("/api/ferramentas/executar", json={"ferramenta": "eco", "alvo": "-n"}).status_code == 422
    assert client.post("/api/ferramentas/executar", json={"ferramenta": "nada", "alvo": "x"}).status_code == 404
    assert client.post("/api/ferramentas/executar", json={"ferramenta": "ausente", "alvo": "prf.gov.br"}).status_code == 503
    assert client.post("/api/ferramentas/executar", json={"ferramenta": "holehe", "alvo": "a@b.co"}).status_code == 403  # sensível desligada
    assert client.get("/api/ferramentas/executar?ferramenta=eco&alvo=x").status_code == 405  # GET só de processos locais
    hist = client.get("/api/ferramentas/historico").json()
    assert len(hist) == 1 and hist[0]["ferramenta"] == "eco" and hist[0]["alvo"] == "PRFBrasil" and hist[0]["ok"] is True
