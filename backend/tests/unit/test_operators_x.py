"""Operadores do X/TweetDeck (strings do boletim Op. Eleições 2026)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.seed import TEMPLATES_OP_ELEICOES
from app.services.operators import TipoToken, operadores_google, operadores_x, tokenizar, validar

pytestmark = pytest.mark.unit

CASOS = json.loads((Path(__file__).resolve().parents[3] / "shared" / "google_operator_cases.json").read_text(encoding="utf-8"))


def codigos(lista) -> set[str]:  # noqa: ANN001
    return {p.codigo for p in lista}


# ---------------------------------------------------------------- paridade back/front (casos_x)
@pytest.mark.parametrize("caso", CASOS["casos_x"], ids=lambda c: c["query"][:40])
def test_paridade_operadores_x_e_google(caso: dict) -> None:
    assert operadores_google(caso["query"]) == caso["google"]
    assert operadores_x(caso["query"]) == caso["x"]


# ---------------------------------------------------------------- strings do boletim
@pytest.mark.parametrize("nome", [n for n, *_ in TEMPLATES_OP_ELEICOES])
def test_templates_op_eleicoes_sao_validos(nome: str) -> None:
    query = next(q for n, _c, _d, q, _p in TEMPLATES_OP_ELEICOES if n == nome)
    r = validar(query)
    assert r.valida, r.erros


def test_string_mobilidade_reconhece_operadores_x() -> None:
    q = next(q for n, _c, _d, q, _p in TEMPLATES_OP_ELEICOES if n.startswith("X — Mobilidade"))
    r = validar(q)
    assert r.valida
    assert r.operadores["-is"] == ["retweet"]
    assert r.operadores["since"] == ["2026-10-04"]
    assert "operador_x" in codigos(r.avisos)
    assert operadores_google(q) == ["()", "OR", '""']  # nenhum operador exclusivo do Google além da sintaxe


def test_string_tweetdeck_com_and() -> None:
    r = validar('(PRF OR "Polícia Rodoviária") AND (impedindo OR impedimento OR blitz OR eleitores)')
    assert r.valida
    assert "and_explicito" in codigos(r.avisos)
    assert TipoToken.AND in {t.tipo for t in r.tokens}


# ---------------------------------------------------------------- since/until
def test_since_until_validos() -> None:
    r = validar("PRF since:2026-10-01 until:2026-10-05")
    assert r.valida and r.operadores == {"since": ["2026-10-01"], "until": ["2026-10-05"]}


def test_janela_since_until_vazia() -> None:
    r = validar("PRF since:2026-10-10 until:2026-10-01")
    assert "janela_temporal_vazia" in codigos(r.erros)
    assert "janela_temporal_vazia" in codigos(validar("PRF since:2026-10-01 until:2026-10-01").erros)


@pytest.mark.parametrize("valor", ["2026-13-01", "01/10/2026", "ontem"])
def test_since_data_invalida(valor: str) -> None:
    assert "data_invalida" in codigos(validar(f"PRF since:{valor}").erros)


def test_since_negado_avisa() -> None:
    r = validar("PRF -since:2026-10-01")
    assert r.valida and "temporal_negado" in codigos(r.avisos)


def test_temporal_misto_google_e_x_avisa() -> None:
    r = validar("PRF after:2026-10-01 since:2026-10-01")
    assert r.valida and "temporal_misto" in codigos(r.avisos)


def test_after_before_continuam_independentes_de_since() -> None:
    # janela Google válida + janela X válida não geram erro cruzado
    assert validar("PRF after:2026-10-01 before:2026-10-05 since:2026-09-01 until:2026-09-02").valida


# ---------------------------------------------------------------- is:/has:/from:/lang:/min_*
def test_is_valores_conhecidos_e_desconhecidos() -> None:
    assert "x_valor_desconhecido" not in codigos(validar("PRF -is:retweet is:reply").avisos)
    assert "x_valor_desconhecido" in codigos(validar("PRF is:foo").avisos)


def test_has_valores() -> None:
    assert "x_valor_desconhecido" not in codigos(validar("PRF has:media has:links").avisos)
    assert "x_valor_desconhecido" in codigos(validar("PRF has:pdf").avisos)


def test_negacao_invalida_avisa() -> None:
    assert "x_negacao_invalida" in codigos(validar("PRF -lang:pt").avisos)
    assert "x_negacao_invalida" not in codigos(validar("PRF -is:retweet -filter:replies").avisos)


def test_from_to_handle() -> None:
    assert validar("from:PRFBrasil to:@PRFBrasil").valida
    assert "x_handle_suspeito" in codigos(validar("from:usuario-com-hifen").avisos)


def test_lang_e_min() -> None:
    assert validar("PRF lang:pt min_faves:10 min_retweets:0").valida
    assert "x_valor_desconhecido" in codigos(validar("PRF lang:portugues").avisos)
    assert "valor_invalido" in codigos(validar("PRF min_faves:muitos").erros)


def test_operador_x_vazio_e_erro() -> None:
    assert "operador_vazio" in codigos(validar("PRF since: 2026-10-04").erros)


# ---------------------------------------------------------------- AND e @
@pytest.mark.parametrize("q", ["AND PRF", "PRF AND", "PRF AND OR blitz", "(AND PRF)"])
def test_and_mal_posicionado(q: str) -> None:
    assert {"and_mal_posicionado", "or_mal_posicionado"} & codigos(validar(q).erros)


def test_and_minusculo_e_palavra() -> None:
    r = validar("prf and blitz")
    assert r.valida and "and_explicito" not in codigos(r.avisos)
    assert all(t.tipo is TipoToken.TERMO for t in r.tokens)


def test_mencao_token_e_positiva() -> None:
    r = validar("@PRFBrasil")
    assert r.valida
    assert r.tokens[0].tipo is TipoToken.MENCAO
    assert "mencao" in codigos(r.avisos)
    assert "somente_exclusoes" not in codigos(r.avisos)


def test_email_nao_e_mencao() -> None:
    tokens, _ = tokenizar("contato@prf.gov.br")
    assert tokens[0].tipo is TipoToken.TERMO


# ---------------------------------------------------------------- regressão: operadores_google ignora X
def test_operadores_google_ignora_operadores_x() -> None:
    assert operadores_google("PRF -is:retweet since:2026-10-04 from:PRFBrasil @PRFBrasil AND blitz") == []
    assert operadores_x("PRF site:gov.br after:2026-10-01") == []


def test_palavras_comuns_nao_viram_operador_x() -> None:
    # "to", "is", "from" só são operadores quando seguidos de ':' sem espaço
    r = validar("vou to is from near within")
    assert r.valida and r.operadores == {} and not any(p.codigo.startswith("x_") for p in r.avisos)
