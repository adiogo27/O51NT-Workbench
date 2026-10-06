from __future__ import annotations

from datetime import date

import pytest

from app.models.agenda import AgendaEvento
from app.models.boletim import BoletimItem, Perfil
from app.services import boletim as svc
from app.services.operators import validar

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("rede", "entrada", "handle", "url"),
    [
        ("x", "@PRFBrasil", "PRFBrasil", "https://x.com/PRFBrasil"),
        ("x", "https://x.com/PRFBrasil?s=20", "PRFBrasil", "https://x.com/PRFBrasil"),
        ("x", "https://twitter.com/#!/PRFBrasil", "PRFBrasil", "https://x.com/PRFBrasil"),
        ("instagram", "https://www.instagram.com/prfbrasil/", "prfbrasil", "https://www.instagram.com/prfbrasil/"),
        ("tiktok", "https://www.tiktok.com/@prf.oficial", "prf.oficial", "https://www.tiktok.com/@prf.oficial"),
        ("youtube", "https://www.youtube.com/@canal", "canal", "https://www.youtube.com/@canal"),
        ("telegram", "https://t.me/s/canal_x", "canal_x", "https://t.me/s/canal_x"),
        ("mastodon", "https://mastodon.social/@user", "user@mastodon.social", "https://mastodon.social/@user"),
        ("mastodon", "user@mastodon.social", "user@mastodon.social", "https://mastodon.social/@user"),
        ("site", "https://exemplo.org/agenda", "https://exemplo.org/agenda", "https://exemplo.org/agenda"),
    ],
)
def test_normalizar_handle_e_url(rede: str, entrada: str, handle: str, url: str) -> None:
    h = svc.normalizar_handle(rede, entrada)
    assert h == handle and svc.url_perfil(rede, h) == url


@pytest.mark.parametrize(("rede", "entrada"), [("x", ""), ("x", "https://instagram.com/x"), ("x", "nome com espaço"), ("mastodon", "semarroba"), ("site", "exemplo.org")])
def test_normalizar_handle_invalido(rede: str, entrada: str) -> None:
    with pytest.raises(ValueError):
        svc.normalizar_handle(rede, entrada)


def test_query_mencoes() -> None:
    p = Perfil(rede="x", handle="PRFBrasil", url="https://x.com/PRFBrasil", rotulo="PRF Brasil")
    ref = date(2026, 10, 5)
    assert svc.query_mencoes(p, "x", ref) == "(from:PRFBrasil OR @PRFBrasil) -is:retweet since:2026-10-04"
    assert svc.query_mencoes(p, "google", ref) == '("PRF Brasil" OR PRFBrasil) after:2026-10-04'
    ig = Perfil(rede="instagram", handle="coletivo", url="u", rotulo="")
    assert svc.query_mencoes(ig, "x", ref) == "coletivo -is:retweet since:2026-10-04"
    for q in (svc.query_mencoes(p, "x", ref), svc.query_mencoes(p, "google", ref)):
        assert validar(q).valida


def test_titulo_boletim_formato_do_documento() -> None:
    assert svc.titulo_boletim(date(2026, 10, 5)) == "INFORMAÇÕES RELEVANTES - 05 OUT 2026 (segunda-feira)"
    assert svc.titulo_boletim(date(2026, 9, 25)) == "INFORMAÇÕES RELEVANTES - 25 SET 2026 (sexta-feira)"


def _ctx() -> dict:
    d = date(2026, 10, 3)
    return {
        "data": d,
        "secoes": {
            "noticia": [BoletimItem(id=1, data=d, secao="noticia", titulo="PRF promete livre deslocamento", url="https://ex.org/n1", fonte="Metrópoles", resumo="Resumo.")],
            "fake_news": [BoletimItem(id=2, data=d, secao="fake_news", titulo="É falso que…", url="https://ex.org/f1", fonte="AFP", evidence_id=9)],
        },
        "agenda": [
            AgendaEvento(id=3, candidato="Candidato A", partido="XYZ", titulo="Carreata", tipo="carreata", data=d, hora_inicio="14:00", cidade="Americana", uf="SP", rodovias="BR-116", impacto_rodovia=True),
            AgendaEvento(id=4, candidato="Candidato B", titulo="Caminhada", tipo="caminhada", data=d, cidade="Goiânia", uf="GO", status="cancelado"),
        ],
        "perfis": [Perfil(id=5, rede="x", handle="PRFBrasil", url="https://x.com/PRFBrasil", rotulo="PRF Brasil", categoria="institucional")],
        "hashtags": ["#Eleicoes2026", "#Brasil2026"],
        "convites": [{"plataforma": "telegram", "url": "https://t.me/+abc", "termo": "x", "last_seen": "2026-10-02"}],
    }


def test_gerar_markdown_segue_a_ordem_do_documento() -> None:
    md = svc.gerar_markdown(_ctx())
    titulos = [l[3:] for l in md.splitlines() if l.startswith("## ")]
    assert titulos == ["HASHTAGS", "NOTÍCIAS RELEVANTES", "FAKE NEWS", "MANIFESTAÇÕES IDENTIFICADAS", "AGENDA DOS CANDIDATOS", "IMAGEM INSTITUCIONAL", "LINKS DE GRUPOS IDENTIFICADOS", "PERFIS PARA ACOMPANHAR", "OUTRAS INFORMAÇÕES"]
    assert md.startswith("# INFORMAÇÕES RELEVANTES - 03 OUT 2026 (sábado)")
    assert "#Eleicoes2026 #Brasil2026" in md
    assert "- **PRF promete livre deslocamento** (Metrópoles) — https://ex.org/n1\n  Resumo." in md
    assert "[evidência #9]" in md
    assert "**Candidato A (XYZ)**\n- 14:00 — Carreata (carreata) — Americana/SP — BR-116 — PODERÁ IMPACTAR O FLUXO VIÁRIO NAS RODOVIAS FEDERAIS" in md
    assert "- — — Caminhada (caminhada) — Goiânia/GO — CANCELADO" in md
    assert "- telegram — https://t.me/+abc (termo: x; visto em 2026-10-02)" in md
    assert "- PRF Brasil — https://x.com/PRFBrasil (x, institucional)" in md
    # seção vazia vira "-" (como nos dias sem conteúdo do boletim)
    assert "## MANIFESTAÇÕES IDENTIFICADAS\n-\n" in md


def test_gerar_html_escapa_e_linka() -> None:
    ctx = _ctx()
    ctx["secoes"]["noticia"][0].titulo = "<script>x</script> & título"
    h = svc.gerar_html(ctx)
    assert h.startswith("<!doctype html>") and "<title>INFORMAÇÕES RELEVANTES - 03 OUT 2026" in h
    assert "&lt;script&gt;x&lt;/script&gt; &amp; título" in h and "<script>x" not in h
    assert '<a href="https://ex.org/n1">https://ex.org/n1</a>' in h
    assert h.count("<h2>") == 9 and "<ul>" in h and "@media print" in h
