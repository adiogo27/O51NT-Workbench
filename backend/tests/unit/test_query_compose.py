from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlsplit

import pytest

from app.schemas.query import BlocoEscopo, BlocoPrecisao, BlocoTemporal, ComposeRequest
from app.seed import TEMPLATES_PDF
from app.services import operators
from app.services.query_compose import citar, compatibilidade, compor, deeplinks, grupo_or, preencher_template

pytestmark = pytest.mark.unit

TPL = {nome: query for nome, _c, _d, query, _p in TEMPLATES_PDF}


def test_citar() -> None:
    assert citar("PRF") == "PRF"
    assert citar("Polícia Rodoviária") == '"Polícia Rodoviária"'
    assert citar('"já citado"') == '"já citado"'
    assert citar('meio "aspas" aqui') == '"meio aspas aqui"'


def test_grupo_or() -> None:
    assert grupo_or(["PRF", "Polícia Rodoviária"]) == '(PRF OR "Polícia Rodoviária")'
    assert grupo_or(["só"]) == "só"
    assert grupo_or(["", " "]) == ""


def test_reconstroi_template_redes_sociais_do_pdf() -> None:
    req = ComposeRequest(
        escopo=BlocoEscopo(sites=["facebook.com", "instagram.com", "x.com", "tiktok.com"]),
        precisao=BlocoPrecisao(grupos_or=[["PRF", "Polícia Rodoviária"], ["Eleições"]]),
        temporal=BlocoTemporal(after=date(2026, 10, 2)),
    )
    # versão corrigida (o PDF esquece o site: antes de tiktok.com)
    assert compor(req) == (
        '(site:facebook.com OR site:instagram.com OR site:x.com OR site:tiktok.com) '
        '(PRF OR "Polícia Rodoviária") Eleições after:2026-10-02'
    )


def test_reconstroi_template_localidade_do_pdf() -> None:
    req = ComposeRequest(
        precisao=BlocoPrecisao(
            grupos_or=[["PRF", "Polícia Rodoviária"], ["Bloqueio", "Blitz"], ["Votar", "Votação"], ["BR", "Rodovia", "Estrada"]]
        ),
        temporal=BlocoTemporal(after=date(2026, 10, 1)),
    )
    assert compor(req) == TPL["Localidade após data"]


def test_blocos_completos_snapshot() -> None:
    req = ComposeRequest(
        precisao=BlocoPrecisao(
            termos=["PRF"], frases_exatas=["Polícia Rodoviária Federal"], excluir=["concurso"], curingas=[["Termo", "Termo2"]]
        ),
        temporal=BlocoTemporal(after=date(2026, 10, 1), before=date(2026, 10, 31)),
        escopo=BlocoEscopo(excluir_sites=["gov.br"], filetype=".PDF", inurl=["PRF"], intitle=["Policia Rodoviária Federal"], intext=["Termo"]),
    )
    q = compor(req)
    assert q == (
        '-site:gov.br filetype:pdf inurl:PRF intitle:"Policia Rodoviária Federal" intext:Termo '
        '"Polícia Rodoviária Federal" PRF "Termo * Termo2" -concurso after:2026-10-01 before:2026-10-31'
    )
    assert operators.validar(q).valida


@pytest.mark.parametrize(
    ("nome", "valores", "esperado"),
    [
        (
            "Convites WhatsApp",
            {"Termo a ser pesquisado": "eleições 2026"},
            '(site:facebook.com OR site:instagram.com OR site:x.com OR site:tiktok.com) (chat.whatsapp.com "eleições 2026")',
        ),
        (
            "Convites Telegram",
            {"Termo a ser pesquisado": "bloqueio"},
            '(site:facebook.com OR site:instagram.com OR site:x.com OR site:tiktok.com) (t.me/joinchat "bloqueio")',
        ),
        ("Acompanhamento por Hashtags", {"#NomeHashTag": "#Eleicoes2026"}, "(site:facebook.com OR site:instagram.com) #Eleicoes2026"),
        ("Depois da data (after)", {"2026-10-01": "2026-11-15"}, "PRF after:2026-11-15"),
        ("Curinga de palavras", {"Termo2": "Federal", "Termo": "Polícia"}, '("Polícia * Federal")'),
    ],
)
def test_preencher_templates_do_pdf(nome: str, valores: dict[str, str], esperado: str) -> None:
    assert preencher_template(TPL[nome], valores) == esperado


def test_compor_com_template_e_blocos() -> None:
    req = ComposeRequest(temporal=BlocoTemporal(after=date(2026, 10, 2)), valores_template={"#NomeHashTag": "#PRF"})
    assert compor(req, TPL["Acompanhamento por Hashtags"]) == "(site:facebook.com OR site:instagram.com) #PRF after:2026-10-02"


@pytest.mark.parametrize("nome", [n for n, *_ in TEMPLATES_PDF])
def test_todos_templates_seedados_sao_validos(nome: str) -> None:
    assert operators.validar(TPL[nome]).valida, nome


def test_deeplinks_codificam_query() -> None:
    q = 'PRF "Polícia Rodoviária" after:2026-10-01'
    links = deeplinks(q)
    assert set(links) == {"google", "bing", "duckduckgo", "startpage"}
    assert parse_qs(urlsplit(links["google"]).query)["q"] == [q]
    assert parse_qs(urlsplit(links["startpage"]).query)["query"] == [q]


def test_compatibilidade() -> None:
    r = operators.validar('"a * b" after:2026-01-01')
    comp = compatibilidade(r.operadores, r.query)
    assert "google" not in comp
    assert comp["bing"] == ["*", "after"]
