from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.cartaz import fabricar_cartaz, imagem_neutra
from tests.unit.test_coletores import BSKY, TME

pytestmark = pytest.mark.integration
WA = "https://chat.whatsapp.com/GM4b5kGzIFm36GoyM7AOlM"
TEXTO_CARTAZ = "GRITO DOS EXCLUÍDOS REVOLTA NAS RUAS DIA 11 DE OUTUBRO EM BELO HORIZONTE, MINAS GERAIS ATO NÃO PACÍFICO"


def _upload(client: TestClient, dados: bytes, **form):  # noqa: ANN003, ANN202
    return client.post("/api/convocacoes/analisar", files={"arquivo": ("cartaz.png", dados, "image/png")}, data={k: str(v) for k, v in form.items()})


def test_analisar_print_cria_deteccao_evidencia_e_alerta(client: TestClient) -> None:
    # `texto` acompanha o print: o teste não depende do OCR estar instalado (um 2º teste exige OCR)
    r = _upload(client, fabricar_cartaz(qr=WA), texto=TEXTO_CARTAZ, plataforma="x", url="https://x.com/alguem/status/1")
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["salva"] and j["nova"] and j["severidade"] == "critica" and j["score"] >= 75
    d = j["deteccao"]
    assert d["nao_pacifico"] and d["data_evento"] == "2026-10-11" and d["local_evento"] == "Belo Horizonte/MG" and d["plataforma"] == "x"
    assert WA in d["qr"] and d["convites"][0]["url"] == WA and d["evidencia_id"]
    assert j["resultado"]["decomposicao"]["bonus_distribuicao"] == 15 and j["resultado"]["lexico"]["nao_pacifico"]
    # evidência com hash + miniatura
    ev = client.get(f"/api/evidence/{d['evidencia_id']}").json()
    assert ev["tipo"] == "imagem" and ev["sha256"] == d["sha256"] and ev["origem_url"] == "https://x.com/alguem/status/1"
    th = client.get(f"/api/convocacoes/{d['id']}/miniatura")
    assert th.status_code == 200 and th.headers["content-type"] == "image/jpeg"
    # alerta persistido + inbox
    assert j["alerta_id"] and d["alerta_id"] == j["alerta_id"]
    alertas = client.get("/api/alertas", params={"tipo": "convocacao"}).json()
    assert len(alertas) == 1 and alertas[0]["severidade"] == "critica" and alertas[0]["deteccao_id"] == d["id"] and "jsonl" in alertas[0]["canal_log"]
    assert client.get("/api/alertas/contagem").json() == {"total": 1, "criticos": 1, "convocacao": 1, "convite": 0, "radar": 0}
    # QR do cartaz foi para a tabela de convites
    conv = client.get("/api/invites").json()
    assert len(conv) == 1 and conv[0]["url"] == WA and conv[0]["fonte_url"] == "https://x.com/alguem/status/1" and conv[0]["origem"] == f"deteccao:{d['id']}"
    # fila
    fila = client.get("/api/convocacoes", params={"estado": "nova"}).json()
    assert [x["id"] for x in fila] == [d["id"]]
    st = client.get("/api/convocacoes/status").json()
    assert st["novas"] == 1 and st["por_severidade"]["critica"] == 1 and st["capacidades"]["lexico"] is True and st["ativo"] is False


def test_reenvio_mesma_imagem_vira_ocorrencia(client: TestClient) -> None:
    dados = fabricar_cartaz()
    a = _upload(client, dados, texto=TEXTO_CARTAZ, url="https://bsky.app/profile/a/post/1", plataforma="bluesky").json()
    b = _upload(client, dados, texto=TEXTO_CARTAZ, url="https://t.me/canal/7", plataforma="telegram").json()
    assert b["duplicada"] and not b["nova"] and b["deteccao"]["id"] == a["deteccao"]["id"] and b["ocorrencia_id"]
    assert b["deteccao"]["ocorrencias"] == 2
    oc = client.get(f"/api/convocacoes/{a['deteccao']['id']}/ocorrencias").json()
    assert len(oc) == 1 and oc[0]["post_url"] == "https://t.me/canal/7" and oc[0]["plataforma"] == "telegram" and oc[0]["variante"] is False
    assert len(client.get("/api/alertas").json()) == 1  # não alerta de novo pela mesma imagem
    assert len(client.get("/api/evidence").json()) == 1


def test_salvar_false_so_analisa(client: TestClient) -> None:
    r = _upload(client, imagem_neutra(), texto="foto da praia", salvar="false").json()
    assert not r["salva"] and r["deteccao"] is None and r["severidade"] == "baixa"
    assert client.get("/api/convocacoes").json() == [] and client.get("/api/alertas").json() == []


def test_analisar_validacoes(client: TestClient) -> None:
    assert client.post("/api/convocacoes/analisar", data={}).status_code == 422
    assert client.post("/api/convocacoes/analisar", data={"url": "ftp://x"}).status_code == 422
    assert client.post("/api/convocacoes/analisar", files={"arquivo": ("a.txt", b"oi", "text/plain")}).status_code == 415
    assert client.post("/api/convocacoes/analisar", files={"arquivo": ("a.png", b"nao-e-imagem", "image/png")}).status_code == 422


def test_so_texto_sem_imagem(client: TestClient) -> None:
    r = client.post("/api/convocacoes/analisar", data={"texto": "Vem pra rua sábado 11/10 às 14h na Praça Sete, BH! Ato não pacífico. Compartilhe", "plataforma": "x"}).json()
    assert r["salva"] and r["deteccao"]["evidencia_id"] is None and r["severidade"] in ("alta", "critica") and r["deteccao"]["origem"] == "texto"


def test_acoes_confirmar_descartar_boletim_agenda(client: TestClient) -> None:
    d = _upload(client, fabricar_cartaz(), texto=TEXTO_CARTAZ, url="https://x.com/a/status/9", plataforma="x").json()["deteccao"]
    did = d["id"]
    c = client.post(f"/api/convocacoes/{did}/confirmar", json={"rotulo": "Grito 11/10"}).json()
    assert c["estado"] == "confirmada" and c["referencia_id"]
    refs = client.get("/api/convocacoes/referencias").json()
    assert len(refs) == 1 and refs[0]["rotulo"] == "Grito 11/10" and refs[0]["phash"] == d["phash"] and refs[0]["tem_embedding"] is False
    assert client.post(f"/api/convocacoes/{did}/confirmar", json={}).status_code == 409
    # uma variante da mesma arte agora casa pela referência (componente referencia = 100)
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.open(io.BytesIO(fabricar_cartaz())).convert("RGB").resize((700, 875)).save(buf, "JPEG", quality=60)
    v = _upload(client, buf.getvalue(), texto="", url="https://instagram.com/p/zz", plataforma="instagram").json()
    assert v["duplicada"] or v["resultado"]["referencia"]["score"] == 100
    # boletim
    b = client.post(f"/api/convocacoes/{did}/boletim", json={"secao": "manifestacao"}).json()
    assert b["secao"] == "manifestacao" and b["data"] == "2026-10-11" and "Belo Horizonte" in b["titulo"] and b["evidence_id"] == d["evidencia_id"]
    assert client.post(f"/api/convocacoes/{did}/boletim", json={}).status_code == 409
    # agenda
    a = client.post(f"/api/convocacoes/{did}/agenda", json={}).json()
    assert a["tipo"] == "ato" and a["data"] == "2026-10-11" and a["cidade"] == "Belo Horizonte" and a["uf"] == "MG" and a["fonte_url"] == "https://x.com/a/status/9"
    assert client.post(f"/api/convocacoes/{did}/agenda", json={}).status_code == 409
    det = client.get(f"/api/convocacoes/{did}").json()
    assert det["boletim_item_id"] == b["id"] and det["agenda_evento_id"] == a["id"]
    # descartar + patch + remover referência
    x = client.post(f"/api/convocacoes/{did}/descartar", json={"motivo": "é notícia"}).json()
    assert x["estado"] == "descartada" and "é notícia" in x["notas"]
    assert client.patch(f"/api/convocacoes/{did}", json={"estado": "nova", "notas": "rever"}).json()["notas"] == "rever"
    assert client.delete(f"/api/convocacoes/referencias/{refs[0]['id']}").status_code == 204
    assert client.get(f"/api/convocacoes/{did}").json()["referencia_id"] is None
    assert client.delete(f"/api/convocacoes/{did}").status_code == 204 and client.get(f"/api/convocacoes/{did}").status_code == 404


def test_monitor_pontua_texto_do_cartaz(client: TestClient) -> None:
    client.post("/api/monitors", json={"nome": "BH", "query": '"ato não pacífico" "belo horizonte"'})
    r = _upload(client, fabricar_cartaz(), texto=TEXTO_CARTAZ).json()
    mons = r["resultado"]["monitores"]
    assert len(mons) == 1 and mons[0]["nome"] == "BH" and set(mons[0]["termos"]) == {'"ato não pacífico"', '"belo horizonte"'}
    assert r["resultado"]["decomposicao"]["componentes"]["monitor"]["valor"] == 100 and "BH:" in r["deteccao"]["termos_monitor"]


def test_analisar_por_url_imagem_direta_e_pagina_og(client: TestClient, fake_fetcher) -> None:  # noqa: ANN001
    fake_fetcher.binarios["https://cdn.test/cartaz.png"] = (200, fabricar_cartaz(), "image/png")
    r = client.post("/api/convocacoes/analisar", data={"url": "https://cdn.test/cartaz.png", "texto": TEXTO_CARTAZ}).json()
    assert r["deteccao"]["imagem_url"] == "https://cdn.test/cartaz.png" and r["deteccao"]["origem"] == "url" and r["deteccao"]["evidencia_id"]
    html = '<html><head><meta property="og:title" content="Revolta nas ruas dia 11/10 em BH"><meta property="og:description" content="ato não pacífico"><meta property="og:image" content="/img/c.png"></head></html>'
    fake_fetcher.paginas["https://t.me/canal/5?embed=1"] = (200, html)
    fake_fetcher.binarios["https://t.me/img/c.png"] = (200, fabricar_cartaz(tamanho=(600, 750)), "image/png")
    r2 = client.post("/api/convocacoes/analisar", data={"url": "https://t.me/canal/5"}).json()
    assert r2["deteccao"]["plataforma"] == "telegram" and r2["deteccao"]["imagem_url"] == "https://t.me/img/c.png" and "Revolta" in r2["deteccao"]["texto_post"]
    assert "GET HTTP 200" in r2["resultado"]["passos"][0]
    assert client.post("/api/convocacoes/analisar", data={"url": "https://nada.test/x"}).status_code == 422


def test_analisar_url_bluesky_via_api_publica(client: TestClient, fake_fetcher) -> None:  # noqa: ANN001
    from app.services.convocacoes import bluesky

    fake_fetcher.paginas[bluesky.url_resolver_handle("coletivo.bsky.social")] = (200, json.dumps({"did": "did:plc:xyz"}))
    fake_fetcher.paginas[bluesky.url_get_posts(bluesky.at_uri("did:plc:xyz", "3kabc"))] = (200, json.dumps({"posts": BSKY["posts"][:1]}))
    fake_fetcher.binarios["https://cdn.bsky.app/img/full/1.jpg"] = (200, fabricar_cartaz(), "image/png")
    r = client.post("/api/convocacoes/analisar", data={"url": "https://bsky.app/profile/coletivo.bsky.social/post/3kabc"}).json()
    d = r["deteccao"]
    assert d["plataforma"] == "bluesky" and d["autor"] == "@coletivo.bsky.social" and "ATO NÃO PACÍFICO" in d["texto_post"] and d["evidencia_id"]
    assert d["publicado_em"].startswith("2026-10-05")


def test_fontes_crud_testar_e_ciclo(client: TestClient, fake_fetcher, fake_searxng) -> None:  # noqa: ANN001
    from app.services.convocacoes import bluesky

    # validações
    assert client.post("/api/convocacoes/fontes", json={"nome": "x", "tipo": "telegram_canal", "parametro": "a b"}).status_code == 422
    assert client.post("/api/convocacoes/fontes", json={"nome": "x", "tipo": "bluesky_busca", "parametro": ""}).status_code == 422
    f1 = client.post("/api/convocacoes/fontes", json={"nome": "Bsky ato", "tipo": "bluesky_busca", "parametro": "ato não pacífico", "rede_alvo": "bluesky"})
    assert f1.status_code == 201
    assert client.post("/api/convocacoes/fontes", json={"nome": "dup", "tipo": "bluesky_busca", "parametro": "ato não pacífico"}).status_code == 409
    f2 = client.post("/api/convocacoes/fontes", json={"nome": "TG", "tipo": "telegram_canal", "parametro": "https://t.me/movimentobrasil"}).json()
    assert f2["parametro"] == "movimentobrasil"
    f3 = client.post("/api/convocacoes/fontes", json={"nome": "Img X", "tipo": "searxng_imagens", "parametro": 'site:x.com "ato não pacífico"', "rede_alvo": "x"}).json()
    # respostas falsas
    fake_fetcher.paginas[bluesky.url_busca("ato não pacífico", limite=50)] = (200, json.dumps(BSKY))
    fake_fetcher.paginas["https://t.me/s/movimentobrasil"] = (200, TME)
    fake_searxng.respostas['site:x.com "ato não pacífico"'] = [
        {"url": "https://x.com/u/status/1", "title": "Revolta nas ruas", "content": "ato 11/10 BH", "img_src": "https://pbs.test/1.jpg", "thumbnail_src": "https://th.test/1.jpg"},
        {"url": "https://x.com/u/status/2", "title": "sem imagem", "content": ""},
    ]
    cartaz = fabricar_cartaz()
    for u in ("https://cdn.bsky.app/img/full/1.jpg", "https://cdn4.telesco.pe/file/a.jpg", "https://pbs.test/1.jpg"):
        fake_fetcher.binarios[u] = (200, cartaz, "image/jpeg")
    fake_fetcher.binarios["https://cdn.bsky.app/img/full/2.jpg"] = (200, imagem_neutra(), "image/jpeg")
    fake_fetcher.binarios["https://cdn4.telesco.pe/file/b.jpg"] = (200, imagem_neutra((641, 480)), "image/jpeg")
    # testar (sem gravar)
    t = client.post("/api/convocacoes/fontes/testar", json={"tipo": "telegram_canal", "parametro": "@movimentobrasil"}).json()
    assert t["ok"] and t["candidatos"] == 3 and t["com_imagem"] == 2 and t["robots_permite"] and t["amostra"][0]["post_url"] == "https://t.me/movimentobrasil/101"
    t2 = client.post("/api/convocacoes/fontes/testar", json={"tipo": "telegram_canal", "parametro": "@inexistente"}).json()
    assert not t2["ok"] and t2["status"] == 404
    assert client.get("/api/convocacoes").json() == []
    # ciclo
    r = client.post("/api/convocacoes/ciclo").json()
    por_tipo = {f["tipo"]: f for f in r["fontes"]}
    assert por_tipo["bluesky_busca"]["candidatos"] == 3 and por_tipo["bluesky_busca"]["analisados"] == 2  # 2 com imagem; o 3º é texto fraco
    assert por_tipo["telegram_canal"]["analisados"] == 2 and por_tipo["searxng_imagens"]["analisados"] == 1
    assert por_tipo["feed_midia"]["candidatos"] == 0  # fonte virtual criada automaticamente
    assert r["novos"] >= 2 and r["ocorrencias"] >= 2 and r["alertas"] >= 1
    dets = client.get("/api/convocacoes").json()
    forte = [d for d in dets if d["severidade"] in ("alta", "critica")]
    assert forte and forte[0]["ocorrencias"] >= 3  # mesmo cartaz em bluesky, telegram e x
    assert {o["plataforma"] for o in client.get(f"/api/convocacoes/{forte[0]['id']}/ocorrencias").json()} >= {"telegram", "x"}
    # 2º ciclo não reanalisa
    r2 = client.post("/api/convocacoes/ciclo").json()
    # (a busca do Bluesky passa a levar `since=` após a 1ª coleta; o fetcher falso não a conhece → 404, sem candidatos)
    assert r2["analisados"] == 0 and all(f.get("pulados", 0) >= 1 for f in r2["fontes"] if f["tipo"] in ("telegram_canal", "searxng_imagens"))
    fontes = client.get("/api/convocacoes/fontes").json()
    assert all(f["ultima_coleta"] for f in fontes) and client.get(f"/api/convocacoes/fontes/{f3['id']}").json()["ultimo_status"] == 200
    assert client.get(f"/api/convocacoes/fontes/{f1.json()['id']}").json()["ultimo_status"] == 404  # 2ª busca com since= não existe no fetcher falso
    assert client.patch(f"/api/convocacoes/fontes/{f3['id']}", json={"ativa": False}).json()["ativa"] is False
    assert client.delete(f"/api/convocacoes/fontes/{f2['id']}").status_code == 204
    st = client.get("/api/convocacoes/status").json()
    assert st["ultimo_ciclo"]["analisados"] == 0 and st["fontes_total"] == 3


def test_orcamento_por_ciclo(client: TestClient, fake_fetcher) -> None:  # noqa: ANN001
    from app.services.convocacoes import bluesky

    cfg = client.get("/api/settings").json()
    cfg["preferencias"]["convocacoesMaxImagensCiclo"] = 1
    assert client.put("/api/settings", json=cfg).status_code == 200
    client.post("/api/convocacoes/fontes", json={"nome": "B", "tipo": "bluesky_busca", "parametro": "ato"})
    fake_fetcher.paginas[bluesky.url_busca("ato", limite=50)] = (200, json.dumps(BSKY))
    fake_fetcher.binarios["https://cdn.bsky.app/img/full/1.jpg"] = (200, fabricar_cartaz(), "image/png")
    fake_fetcher.binarios["https://cdn.bsky.app/img/full/2.jpg"] = (200, imagem_neutra(), "image/jpeg")
    r = client.post("/api/convocacoes/ciclo").json()
    assert r["analisados"] == 1 and r["orcamento_restante"] == 0


def test_capacidades_descarregar_e_health(client: TestClient) -> None:
    c = client.get("/api/convocacoes/capacidades").json()
    assert c["perfil"] == "leve" and c["qr"] and c["lexico"] and isinstance(c["ocr_instalado"], bool)
    d = client.post("/api/convocacoes/descarregar").json()
    assert d["carregados"] == []
    h = client.get("/api/health").json()
    assert h["ml"]["perfil"] == "leve"


def test_settings_validacao_limiares(client: TestClient) -> None:
    cfg = client.get("/api/settings").json()
    cfg["preferencias"]["convocacoesLimiarAlerta"] = 80
    cfg["preferencias"]["convocacoesLimiarCritico"] = 70
    assert client.put("/api/settings", json=cfg).status_code == 422


@pytest.mark.ml
def test_ocr_le_o_cartaz_sem_texto_auxiliar(client: TestClient) -> None:
    pytest.importorskip("rapidocr")
    r = _upload(client, fabricar_cartaz(), plataforma="instagram").json()
    d = r["deteccao"]
    assert "PACÍFICO" in d["texto_ocr"].upper() or "PACIFICO" in d["texto_ocr"].upper()
    assert d["ocr_confianca"] > 0.8 and d["severidade"] == "critica" and d["data_evento"] == "2026-10-11" and d["local_evento"] == "Belo Horizonte/MG"
