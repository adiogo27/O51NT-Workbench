from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.unit.test_radar_service import ATOM, RSS

pytestmark = pytest.mark.integration


def test_fontes_seedadas_e_catalogo(client: TestClient) -> None:
    fontes = client.get("/api/radar/fontes").json()
    from app.seed import FONTES_PADRAO, FONTES_PADRAO_SEM_ROBOTS

    assert len(fontes) == len(FONTES_PADRAO) >= 11 and all(f["ativa"] for f in fontes)
    por_url = {f["url"]: f for f in fontes}
    assert all(por_url[u]["respeitar_robots"] is False for u in FONTES_PADRAO_SEM_ROBOTS) and por_url["https://g1.globo.com/rss/g1/politica/"]["respeitar_robots"] is True
    assert {"g1 — política", "Agência Brasil — política", "Mastodon — #eleicoes2026 (mastodon.social)"} <= {f["nome"] for f in fontes}
    cat = client.get("/api/radar/fontes/catalogo").json()
    assert all(c["cadastrada"] for c in cat if c["tipo"] == "feed")
    modelos = [c for c in cat if c["tipo"] == "modelo"]
    assert {"Google Alertas (feed pessoal)", "Mastodon — hashtag (qualquer instância)", "Google Notícias — busca (RSS por termo)", "YouTube — canal (feed de vídeos)", "Reddit — subreddit (novos)"} <= {m["nome"] for m in modelos}
    assert all(not m["cadastrada"] for m in modelos)


def test_fontes_crud_e_teste(client: TestClient, fake_fetcher) -> None:  # noqa: ANN001
    fake_fetcher.paginas["https://feeds.test/a.xml"] = (200, RSS)
    t = client.post("/api/radar/fontes/testar", json={"url": "https://feeds.test/a.xml"}).json()
    assert t["ok"] and t["itens"] == 2 and t["robots_permite"] and t["amostra"][0]["url"] == "https://ex.org/n1"
    t404 = client.post("/api/radar/fontes/testar", json={"url": "https://feeds.test/nada.xml"}).json()
    assert not t404["ok"] and t404["status"] == 404
    assert client.post("/api/radar/fontes/testar", json={"url": "feeds.test"}).status_code == 422

    r = client.post("/api/radar/fontes", json={"nome": "Teste A", "url": "https://feeds.test/a.xml", "categoria": "imprensa"})
    assert r.status_code == 201
    fid = r.json()["id"]
    assert client.post("/api/radar/fontes", json={"nome": "dup", "url": "https://feeds.test/a.xml"}).status_code == 409
    assert client.patch(f"/api/radar/fontes/{fid}", json={"ativa": False, "respeitar_robots": False}).json()["respeitar_robots"] is False
    c = client.post(f"/api/radar/fontes/{fid}/coletar").json()
    assert c["itens_novos"] == 2 and c["fontes"][0]["status"] == 200
    assert client.get(f"/api/radar/fontes/{fid}").json()["itens_total"] == 2
    itens = client.get("/api/radar/itens", params={"fonte_id": fid}).json()
    assert len(itens) == 2 and itens[0]["fonte_nome"] == "Teste A"
    assert len(client.get("/api/radar/itens", params={"q": "concurso"}).json()) == 1
    assert client.delete(f"/api/radar/fontes/{fid}").status_code == 204
    assert client.get("/api/radar/itens", params={"fonte_id": fid}).json() == []  # cascade


def test_ciclo_hits_monitores_e_boletim(client: TestClient, fake_fetcher) -> None:  # noqa: ANN001
    fake_fetcher.paginas["https://feeds.test/a.xml"] = (200, RSS)
    fake_fetcher.paginas["https://feeds.test/c.xml"] = (200, ATOM)
    for f in client.get("/api/radar/fontes").json():  # as seedadas dariam 404 no fetcher falso; desliga para o teste ficar legível
        client.patch(f"/api/radar/fontes/{f['id']}", json={"ativa": False})
    client.post("/api/radar/fontes", json={"nome": "A", "url": "https://feeds.test/a.xml"})
    client.post("/api/radar/fontes", json={"nome": "C", "url": "https://feeds.test/c.xml", "categoria": "rede"})
    m1 = client.post("/api/monitors", json={"nome": "blitz", "query": "PRF blitz"}).json()
    m2 = client.post("/api/monitors", json={"nome": "estrito", "query": "site:x.com PRF", "radar_modo": "estrito"}).json()
    assert m2["radar_modo"] == "estrito"
    assert client.post("/api/monitors", json={"nome": "x", "query": "q", "radar_modo": "livre"}).status_code == 422

    r = client.post("/api/radar/ciclo").json()
    assert r["itens_novos"] == 4 and r["hits_por_monitor"] == {str(m1["id"]): 1} and r["alertas"] == 1

    st = client.get("/api/radar/status").json()
    assert st["ativo"] and st["intervalo_min"] == 10 and st["agendado"] is False  # scheduler desligado nos testes
    assert st["fontes_ativas"] == 2 and st["monitores_ativos"] == 2 and st["itens_total"] == 4 and st["hits_total"] == 1 and st["hits_novos"] == 1
    assert st["ultimo_ciclo"]["hits_novos"] == 1

    mons = {m["id"]: m for m in client.get("/api/monitors").json()}
    assert mons[m1["id"]]["hits_total"] == 1 and mons[m1["id"]]["hits_novos"] == 1 and mons[m2["id"]]["hits_total"] == 0

    hits = client.get("/api/radar/hits").json()
    assert len(hits) == 1 and hits[0]["monitor_nome"] == "blitz" and hits[0]["termos"] == "PRF | blitz" and hits[0]["fonte_nome"] == "A"
    hid = hits[0]["id"]
    assert client.get(f"/api/monitors/{m1['id']}/hits").json()[0]["id"] == hid
    assert client.get("/api/radar/hits", params={"monitor_id": m2["id"]}).json() == []

    # run-now do monitor inclui o resumo do radar no resultado
    run = client.post(f"/api/monitors/{m1['id']}/run-now").json()
    assert run["resultado"]["radar"]["novos_hits"] == 0 and "radar:" in run["log"]

    # novo monitor já nasce casado com o cache
    m3 = client.post("/api/monitors", json={"nome": "carreata", "query": "carreata OR motociata"}).json()
    assert client.get(f"/api/monitors/{m3['id']}/hits").json()[0]["url"] == "https://ex.org/a1"

    # hit → boletim
    b = client.post(f"/api/radar/hits/{hid}/boletim", json={"secao": "noticia"})
    assert b.status_code == 201 and b.json()["fonte"] == "A" and b.json()["url"] == "https://ex.org/n1" and b.json()["data"] == "2026-10-05"
    assert client.post(f"/api/radar/hits/{hid}/boletim", json={}).status_code == 409
    h = client.get(f"/api/radar/hits", params={"monitor_id": m1["id"]}).json()[0]
    assert h["lido"] is True and h["boletim_item_id"] == b.json()["id"]
    assert client.get("/api/boletim/itens", params={"secao": "noticia"}).json()[0]["titulo"].startswith("PRF reforça")

    assert client.patch(f"/api/radar/hits/{hid}", json={"lido": False}).json()["lido"] is False
    assert client.post("/api/radar/hits/marcar-todos").json() == {"marcados": 2}
    assert client.get("/api/radar/hits", params={"lidos": "false"}).json() == []
    assert client.get("/api/radar/hits/99999/boletim").status_code in (404, 405)


def test_settings_radar(client: TestClient) -> None:
    cfg = client.get("/api/settings").json()
    assert cfg["preferencias"]["radarAtivo"] is True and cfg["preferencias"]["radarIntervaloMin"] == 10
    cfg["preferencias"]["radarIntervaloMin"] = 1
    assert client.put("/api/settings", json=cfg).status_code == 422
    cfg["preferencias"]["radarIntervaloMin"] = 30
    cfg["preferencias"]["radarAtivo"] = False
    r = client.put("/api/settings", json=cfg).json()
    assert r["preferencias"]["radarIntervaloMin"] == 30 and r["preferencias"]["radarAtivo"] is False
    assert client.get("/api/radar/status").json()["ativo"] is False


def test_run_now_repetido_usa_ultima_execucao(client: TestClient, fake_fetcher) -> None:  # noqa: ANN001
    """2ª execução: `ultima_execucao` vem do banco e vira o `desde` do casamento (sem erro de fuso)."""
    fake_fetcher.paginas["https://feeds.test/a.xml"] = (200, RSS)
    for f in client.get("/api/radar/fontes").json():
        client.patch(f"/api/radar/fontes/{f['id']}", json={"ativa": False})
    client.post("/api/radar/fontes", json={"nome": "A", "url": "https://feeds.test/a.xml"})
    mid = client.post("/api/monitors", json={"nome": "prf", "query": "PRF"}).json()["id"]
    r1 = client.post(f"/api/monitors/{mid}/run-now").json()
    assert r1["status"] == "ok" and r1["resultado"]["radar"]["novos_hits"] == 0
    client.post("/api/radar/ciclo")  # chegam 2 itens com PRF → viram hits do radar
    r2 = client.post(f"/api/monitors/{mid}/run-now").json()
    assert r2["status"] == "ok" and r2["resultado"]["radar"]["novos_hits"] == 0  # já casados pelo ciclo, sem duplicar
    assert client.get(f"/api/monitors/{mid}").json()["ultima_execucao"] is not None
    assert len(client.get(f"/api/monitors/{mid}/hits").json()) == 2


def test_track_hashtag_cria_fonte_mastodon(client: TestClient) -> None:
    antes = len(client.get("/api/radar/fontes").json())
    client.post("/api/hashtags/track", json={"tag": "#EleNão", "cron": "0 * * * *"})
    fontes = client.get("/api/radar/fontes").json()
    assert len(fontes) == antes + 1
    auto = next(f for f in fontes if "(auto)" in f["nome"])
    assert auto["url"] == "https://mastodon.social/tags/EleN%C3%A3o.rss" and auto["categoria"] == "rede" and auto["ativa"]
    client.post("/api/hashtags/track", json={"tag": "#EleNão", "cron": "0 * * * *"})  # não duplica
    assert len(client.get("/api/radar/fontes").json()) == antes + 1
