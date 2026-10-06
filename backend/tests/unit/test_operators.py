from __future__ import annotations

import pytest

from app.services.operators import TipoToken, tokenizar, validar

pytestmark = pytest.mark.unit


def codigos(lista) -> set[str]:  # noqa: ANN001
    return {p.codigo for p in lista}


# ---------------------------------------------------------------- precisão
@pytest.mark.parametrize(
    "q",
    [
        '"Polícia Rodoviária Federal"',
        '"Policia Rodoviária Federal" -concurso',
        'PRF OR "Polícia Rodoviária"',
        '(PRF OR "Policia Rodoviária")',
        '("Termo * Termo2")',
    ],
)
def test_precisao_validos_do_pdf(q: str) -> None:
    r = validar(q)
    assert r.valida, r.erros


def test_frase_exata_vira_um_token() -> None:
    tokens, erros = tokenizar('"Polícia Rodoviária Federal"')
    assert not erros
    assert [t.tipo for t in tokens] == [TipoToken.FRASE]


def test_exclusao_marca_negado() -> None:
    tokens, _ = tokenizar('"PRF" -concurso')
    assert tokens[1].negado and tokens[1].valor == "concurso"


def test_exclusao_de_frase() -> None:
    tokens, _ = tokenizar('PRF -"concurso público"')
    assert tokens[1].tipo is TipoToken.FRASE and tokens[1].negado


def test_aspas_desbalanceadas() -> None:
    r = validar('("Termo * Termo2)')  # exemplo literal do PDF
    assert not r.valida
    assert "aspas_desbalanceadas" in codigos(r.erros)


@pytest.mark.parametrize("q", ["(PRF OR PF", "PRF OR PF)", "((a) b", ")("])
def test_parenteses_desbalanceados(q: str) -> None:
    r = validar(q)
    assert "parenteses_desbalanceados" in codigos(r.erros)


@pytest.mark.parametrize("q", ["OR PRF", "PRF OR", "PRF OR OR PF", "(OR PRF)", "(PRF OR)"])
def test_or_mal_posicionado(q: str) -> None:
    assert "or_mal_posicionado" in codigos(validar(q).erros)


def test_or_minusculo_avisa() -> None:
    r = validar("PRF or PF")
    assert r.valida and "or_minusculo" in codigos(r.avisos)


def test_curinga_fora_de_aspas_avisa() -> None:
    r = validar("Termo * Termo2")
    assert r.valida and "curinga_fora_aspas" in codigos(r.avisos)


def test_grupo_vazio() -> None:
    assert "grupo_vazio" in codigos(validar("PRF ()").avisos)


# ---------------------------------------------------------------- temporal
def test_before_e_after_validos() -> None:
    r = validar("PRF after:2026-10-01 before:2026-10-31")
    assert r.valida
    assert r.operadores == {"after": ["2026-10-01"], "before": ["2026-10-31"]}


@pytest.mark.parametrize("q", ["PRF before:2026-10-01", "PRF after:2026-10-01"])
def test_temporais_do_pdf(q: str) -> None:
    assert validar(q).valida


def test_janela_temporal_vazia() -> None:
    r = validar("PRF after:2026-10-10 before:2026-10-01")
    assert "janela_temporal_vazia" in codigos(r.erros)


def test_janela_temporal_mesmo_dia_invalida() -> None:
    assert "janela_temporal_vazia" in codigos(validar("x after:2026-10-01 before:2026-10-01").erros)


@pytest.mark.parametrize("valor", ["2026-13-01", "2026-02-30", "01/10/2026", "2026-1-1", "ontem"])
def test_data_invalida(valor: str) -> None:
    assert "data_invalida" in codigos(validar(f"PRF after:{valor}").erros)


def test_temporal_repetido_avisa() -> None:
    r = validar("x after:2026-01-01 after:2026-02-01")
    assert r.valida and "temporal_repetido" in codigos(r.avisos)


# ---------------------------------------------------------------- escopo
@pytest.mark.parametrize(
    "q",
    ['site:uol.com.br "Termo"', 'filetype:pdf "termo"', "inurl:PRF", 'intitle:"Policia Rodoviária Federal"', 'intext:"Termo"'],
)
def test_escopo_do_pdf(q: str) -> None:
    assert validar(q).valida


def test_menos_site_sozinho_avisa_somente_exclusoes() -> None:
    r = validar("-site:gov.br")
    assert r.valida
    assert r.operadores == {"-site": ["gov.br"]}
    assert "somente_exclusoes" in codigos(r.avisos)


def test_site_conflitante() -> None:
    r = validar("PRF site:gov.br -site:gov.br")
    assert "site_conflitante" in codigos(r.erros)


def test_site_conflitante_normaliza_www_e_esquema() -> None:
    r = validar("PRF site:www.uol.com.br -site:https://uol.com.br/")
    assert "site_conflitante" in codigos(r.erros)


def test_site_subdominio_excluido_avisa() -> None:
    r = validar("PRF site:prf.gov.br -site:gov.br")
    assert r.valida and "site_subdominio_excluido" in codigos(r.avisos)


def test_operador_vazio() -> None:
    assert "operador_vazio" in codigos(validar("site: uol.com.br").erros)


def test_filetype_invalido() -> None:
    assert "filetype_invalido" in codigos(validar("filetype:p.d.f x").erros)


def test_intitle_com_aspas_desbalanceadas() -> None:
    assert "aspas_desbalanceadas" in codigos(validar('intitle:"PRF').erros)


def test_site_ausente_em_grupo_literal_do_pdf() -> None:
    q = '(site:facebook.com OR site:instagram.com OR site:x.com OR tiktok.com) (PRF OR "Polícia Rodoviária") (Eleições) after:2026-10-02'
    r = validar(q)
    assert r.valida
    assert "site_ausente" in codigos(r.avisos)


def test_operador_sem_dois_pontos_avisa() -> None:
    assert "operador_sem_dois_pontos" in codigos(validar("inurl PRF").avisos)


def test_urls_nao_viram_operador() -> None:
    tokens, _ = tokenizar('(chat.whatsapp.com "x") https://t.me/joinchat')
    assert all(t.tipo is not TipoToken.OPERADOR for t in tokens)


def test_hashtag_token() -> None:
    tokens, _ = tokenizar("(site:facebook.com OR site:instagram.com) #NomeHashTag")
    assert tokens[-1].tipo is TipoToken.HASHTAG


def test_query_vazia() -> None:
    assert "query_vazia" in codigos(validar("   ").erros)


def test_complexidade_linear_string_grande() -> None:
    q = " ".join(f"(t{i} OR \"frase {i}\")" for i in range(5000))
    r = validar(q)
    assert r.valida
    assert len(r.tokens) == 5000 * 5


# ---------------------------------------------------------------- operadores exclusivos do Google (paridade c/ frontend)
def _casos_compartilhados() -> list[dict]:
    import json
    from pathlib import Path

    arq = Path(__file__).resolve().parents[3] / "shared" / "google_operator_cases.json"
    return json.loads(arq.read_text(encoding="utf-8"))["casos"]


@pytest.mark.parametrize("caso", _casos_compartilhados(), ids=lambda c: c["query"][:40])
def test_operadores_google_paridade(caso: dict) -> None:
    from app.services.operators import operadores_google

    assert operadores_google(caso["query"]) == caso["esperado"]


def test_convites_casos_compartilhados_batem_com_backend() -> None:
    """As queries da aba Convites usam operadores do Google → SearXNG desabilitado (paridade c/ Vitest)."""
    import json
    from pathlib import Path

    from app.routers.invites import montar_queries
    from app.services.operators import operadores_google

    arq = Path(__file__).resolve().parents[3] / "shared" / "google_operator_cases.json"
    conv = json.loads(arq.read_text(encoding="utf-8"))["convites"]
    reais = montar_queries(conv["termo"])
    for caso in conv["casos"]:
        assert reais[caso["plataforma"]] == caso["query"]
        assert operadores_google(caso["query"]) == caso["esperado"]
