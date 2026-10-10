"""Bloco X/TweetDeck no Query Builder: contrato original preservado + campos adicionais."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

MOBILIDADE = (
    '(rodovia OR rodovias OR "BR-101" OR "BR-116" OR "BR-040") (bloqueio OR interdição OR carreata OR blitz) '
    "-is:retweet since:2026-10-04"
)


def test_compose_com_bloco_x(client: TestClient) -> None:
    r = client.post(
        "/api/query/compose",
        json={
            "precisao": {"termos": ["PRF"]},
            "x": {"from": ["@PRFBrasil"], "excluir_retweets": True, "since": "2026-10-04", "lang": "pt", "min_faves": 10},
        },
    ).json()
    assert r["query"] == "PRF from:PRFBrasil -is:retweet lang:pt min_faves:10 since:2026-10-04"
    assert r["valida"]
    assert r["operadores_x"] == ["from:", "-is:", "lang:", "min_faves:", "since:"]
    # contrato original intacto
    assert set(r["deeplinks"]) == {"google", "bing", "duckduckgo", "startpage"}
    # campos adicionais
    assert {"x", "tiktok", "youtube", "google_news"} <= set(r["deeplinks_extra"])  # os 4 originais + buscadores/redes de 2026-10-10
    assert {"brave", "yandex", "mojeek", "bing_news", "bluesky", "threads", "reddit"} <= set(r["deeplinks_extra"])
    assert parse_qs(urlsplit(r["deeplinks_extra"]["brave"]).query)["q"] == [r["query"]]
    x = urlsplit(r["deeplinks_extra"]["x"])
    assert x.netloc == "x.com" and parse_qs(x.query)["q"] == [r["query"]] and parse_qs(x.query)["f"] == ["live"]
    assert "since" in r["compatibilidade"]["google"]  # Google ignora operadores do X
    assert "x" not in r["compatibilidade_extra"]  # nada que o X não suporte


def test_compose_sem_bloco_x_mantem_comportamento(client: TestClient) -> None:
    r = client.post("/api/query/compose", json={"precisao": {"termos": ["PRF"]}, "temporal": {"after": "2026-10-01"}}).json()
    assert r["query"] == "PRF after:2026-10-01"
    assert r["operadores_x"] == []
    assert r["compatibilidade_extra"]["x"] == ["after"]  # X não entende after:
    assert "google" not in r["compatibilidade"]


def test_compose_janela_x_invalida(client: TestClient) -> None:
    r = client.post("/api/query/compose", json={"precisao": {"termos": ["PRF"]}, "x": {"since": "2026-10-10", "until": "2026-10-01"}}).json()
    assert not r["valida"] and r["erros"][0]["codigo"] == "janela_temporal_vazia"


def test_validate_string_do_boletim(client: TestClient) -> None:
    r = client.post("/api/query/validate", json={"query": MOBILIDADE}).json()
    assert r["valida"]
    assert r["operadores"]["-is"] == ["retweet"] and r["operadores"]["since"] == ["2026-10-04"]
    assert "operador_x" in {a["codigo"] for a in r["avisos"]}
    assert r["operadores_x"] == ["-is:", "since:"]
    assert r["compatibilidade"]["google"] == ["is", "since"]
    assert r["compatibilidade_extra"]["tiktok"] == ["is", "since"]
    assert r["deeplinks_extra"]["x"].startswith("https://x.com/search?q=")


def test_templates_op_eleicoes_seedados(client: TestClient) -> None:
    tpls = client.get("/api/query/templates").json()
    nomes = {t["nome"] for t in tpls}
    assert {"X — Mobilidade em rodovias federais", "X — Imagem institucional da PRF", "X/TweetDeck — Imagem institucional PRF (AND)"} <= nomes
    tpl = next(t for t in tpls if t["nome"] == "X — Mobilidade em rodovias federais")
    assert tpl["categoria"] == "x_tweetdeck" and tpl["placeholders"] == ["2026-10-04"]
    r = client.post("/api/query/compose", json={"template_id": tpl["id"], "valores_template": {"2026-10-04": "2026-10-06"}}).json()
    assert r["valida"] and r["query"].endswith("since:2026-10-06")


def test_monitor_run_inclui_deeplinks_extra(client: TestClient) -> None:
    mid = client.post("/api/monitors", json={"nome": "x", "query": "PRF -is:retweet since:2026-10-04"}).json()["id"]
    run = client.post(f"/api/monitors/{mid}/run-now").json()
    assert {"google", "x", "tiktok", "youtube", "google_news"} <= set(run["deeplinks"])
