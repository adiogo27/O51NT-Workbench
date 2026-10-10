"""Unidades do assistente de IA: normalização de URL, extração de JSON/texto, esquemas, páginas HTML, ferramentas."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.models.radar import Fonte
from app.services import ferramentas, radar
from app.services.ia import esquemas, pipeline
from app.services.ia.cliente_openclaw import RespostaInvalida, estimar_custo, extrair_json

pytestmark = pytest.mark.unit


def test_normalizar_url_dedupe_entre_monitores() -> None:
    a = pipeline.normalizar_url("https://WWW.G1.com/noticia/x/?utm_source=tw&fbclid=1&id=2#topo")
    b = pipeline.normalizar_url("https://g1.com/noticia/x?id=2")
    assert a == b == "https://g1.com/noticia/x?id=2"
    assert pipeline.normalizar_url("deteccao:7") == "deteccao:7"


def test_extrair_json_tolerante() -> None:
    assert extrair_json('{"a": 1}') == {"a": 1}
    assert extrair_json('Claro! ```json\n{"veredito": "RELEVANTE", "n": {"x": [1, 2]}}\n``` fim') == {"veredito": "RELEVANTE", "n": {"x": [1, 2]}}
    assert extrair_json('prosa antes {"ok": true} prosa depois')["ok"] is True
    for ruim in ("", "sem json", "[1,2]", "{quebrado"):
        with pytest.raises(RespostaInvalida):
            extrair_json(ruim)


def test_estimar_custo_por_modelo() -> None:
    # lista de preços da Anthropic (2026-10): Haiku 5.5 = 0,10/0,50; Haiku 4.5 = 1/5; Sonnet 5.5 = 2/10; Opus 5.5 = 4/20
    assert estimar_custo("claude-haiku-5-5", 1_000_000, 0) == 0.1
    assert estimar_custo("claude-haiku-4-5", 1_000_000, 0) == 1.0
    assert estimar_custo("anthropic/claude-sonnet-5-5", 0, 1_000_000) == 10.0
    assert estimar_custo("anthropic/claude-opus-5-5", 1_000_000, 0) == 4.0
    assert estimar_custo("desconhecido", 1_000_000, 0) == 3.0  # desconhecido: estimativa conservadora


def test_esquemas_normalizam_valores() -> None:
    t = esquemas.TriagemOut.model_validate({"veredito": "relevante", "severidade": "Crítica", "justificativa": "  x  y ", "tags": "a, b", "secao": "manifestacao"})
    assert t.veredito == "RELEVANTE" and t.severidade == "critica" and t.justificativa == "x y" and t.tags == ["a", "b"]
    with pytest.raises(ValidationError):
        esquemas.TriagemOut.model_validate({"veredito": "TALVEZ"})
    e = esquemas.EventoOut.model_validate({"tipo": "ato", "data": "2026-10-12", "rodovias": "BR-116, BR 101", "confianca": 80, "_notas": "ok", "uf": "pr"})
    assert e.rodovias == ["BR-116", "BR 101"] and e.confianca == 0.8 and e.notas == "ok" and e.uf == "pr"
    p = esquemas.PesquisaOut.model_validate({"resposta": "r", "fontes": ["https://a.b/c", "nao-url", {"url": "https://d.e", "titulo": "t"}], "confianca": "0.5"})
    assert [f.url for f in p.fontes] == ["https://a.b/c", "https://d.e"] and p.confianca == 0.5
    c = esquemas.CartaoOut.model_validate({"titulo": "T", "fontes": [{"url": "https://x.y"}, "https://x.y", "ftp://z"]})
    assert c.fontes == ["https://x.y"]


def test_extrair_texto_fallback_bs4() -> None:
    html = "<html><head><title>t</title><script>var x=1</script></head><body><nav>menu menu</nav><article><p>" + ("Texto da matéria. " * 30) + "</p></article><footer>rodapé</footer></body></html>"
    texto = pipeline.extrair_texto(html, max_chars=200)
    assert texto.startswith("Texto da matéria.") and "menu" not in texto and "rodapé" not in texto and len(texto) <= 200


PAGINA = """<html><head><title>Portal</title>
<link rel="alternate" type="application/rss+xml" href="/feed/rss.xml">
</head><body>
<nav><a href="/politica">Política</a><a href="/economia/noticias-de-economia-hoje">Economia: tudo sobre notícias de hoje</a></nav>
<main>
 <a href="/noticia/2026/10/prf-faz-operacao-na-br-116-e-prende-suspeitos">PRF faz operação na BR-116 e prende suspeitos em Curitiba</a>
 <a href="https://www.portal.test/noticia/2026/10/prf-faz-operacao-na-br-116-e-prende-suspeitos">PRF faz operação na BR-116 e prende suspeitos em Curitiba</a>
 <a href="/noticia/2026/10/carreata-convoca-ato-no-domingo-em-sao-paulo?utm=x#c">Carreata convoca ato no domingo em São Paulo</a>
 <a href="/x">curto</a>
 <a href="https://outro.test/noticia-longa-de-outro-site-que-nao-conta">Notícia longa de outro site que não conta</a>
 <a href="/arquivo/cartaz.jpg">Cartaz do ato de domingo em alta resolução</a>
 <a href="mailto:a@b.c">Fale com a redação pelo e-mail institucional</a>
</main>
<footer><a href="/sobre/quem-somos-e-nossa-historia">Quem somos e nossa história completa</a></footer>
</body></html>"""


def test_parse_pagina_descobrir_feed_e_hash() -> None:
    itens = radar.parse_pagina(PAGINA, "https://portal.test/")
    urls = [i.url for i in itens]
    assert urls == [
        "https://portal.test/noticia/2026/10/prf-faz-operacao-na-br-116-e-prende-suspeitos",
        "https://portal.test/noticia/2026/10/carreata-convoca-ato-no-domingo-em-sao-paulo?utm=x",
    ]
    assert itens[0].titulo.startswith("PRF faz operação")
    assert radar.descobrir_feed(PAGINA, "https://portal.test/") == "https://portal.test/feed/rss.xml"
    assert radar.descobrir_feed("<html><body>nada</body></html>", "https://portal.test/") is None
    assert radar.hash_conteudo(PAGINA) == radar.hash_conteudo(PAGINA.replace("\n", "\n  ")) != radar.hash_conteudo(PAGINA + "<p>novo</p>")
    assert radar.parse_pagina("", "https://portal.test/") == []


def test_fonte_devida_respeita_intervalo() -> None:
    agora_ = datetime.now(UTC)
    f = Fonte(nome="p", url="https://p.test/", tipo="pagina")
    assert radar.fonte_devida(f, agora_)  # sem intervalo
    f.intervalo_min = 60
    assert radar.fonte_devida(f, agora_)  # nunca coletada
    f.ultima_coleta = agora_ - timedelta(minutes=10)
    assert not radar.fonte_devida(f, agora_)
    f.ultima_coleta = (agora_ - timedelta(minutes=61)).replace(tzinfo=None)  # SQLite devolve sem fuso
    assert radar.fonte_devida(f, agora_)


def test_validar_alvo_recusa_injecao() -> None:
    assert ferramentas.validar_alvo("dominio", " https://WWW.PRF.gov.br/path ") == "prf.gov.br"
    assert ferramentas.validar_alvo("usuario", "@PRFBrasil") == "PRFBrasil"
    assert ferramentas.validar_alvo("email", "Pessoa@Exemplo.com") == "pessoa@exemplo.com"
    assert ferramentas.validar_alvo("telefone", "+5561999999999") == "+5561999999999"
    assert ferramentas.validar_alvo("url", "https://www.youtube.com/watch?v=abc") == "https://www.youtube.com/watch?v=abc"
    for tipo, alvo in (("dominio", "prf.gov.br; rm -rf /"), ("dominio", "-x"), ("usuario", "a b"), ("usuario", "x"), ("email", "sem-arroba"), ("telefone", "abc"), ("url", "ftp://x"), ("dominio", "x$(id)"), ("dominio", "a`b`.c")):
        with pytest.raises(ferramentas.ErroFerramenta):
            ferramentas.validar_alvo(tipo, alvo)
    with pytest.raises(ferramentas.ErroFerramenta):
        ferramentas.validar_alvo("evidencia", "12")  # sem sessão


def test_catalogo_ferramentas_marca_sensiveis() -> None:
    cat = ferramentas.catalogo(prefs_sensiveis=False)
    ids = {f["id"] for f in cat}
    assert {"whois", "dig", "sherlock", "maigret", "exiftool", "ytdlp", "holehe", "h8mail", "phoneinfoga", "theharvester", "subfinder", "dnsrecon"} <= ids
    assert all(not f["habilitada"] for f in cat if f["sensivel"]) and all(f["habilitada"] for f in cat if not f["sensivel"])
    assert not any(x in ids for x in ("nmap", "masscan", "nuclei", "hydra", "sqlmap", "gobuster", "wpscan"))


# ---------------------------------------------------------------- camada de verificação (OOVS 0.1.0)
def test_dominio_registravel() -> None:
    from app.services.ia.verificacao import dominio_registravel

    assert dominio_registravel("https://www.g1.globo.com/x") == "globo.com"
    assert dominio_registravel("https://agenciabrasil.ebc.com.br/y") == "ebc.com.br"
    assert dominio_registravel("https://m.folha.uol.com.br/poder/") == "uol.com.br"
    assert dominio_registravel("https://www.gov.br/prf/pt-br") == "gov.br"
    assert dominio_registravel("https://mastodon.social/@x") == "mastodon.social"
    assert dominio_registravel("sem-url") == "" and dominio_registravel("") == ""


def test_origens_distintas_contam_origens_e_nao_mencoes() -> None:
    """OOVS: três cópias da mesma nota de agência = uma origem; a fonte do próprio item não é corroboração."""
    from app.services.ia.verificacao import agrupar_origens

    nota = "A Polícia Rodoviária Federal informou que a BR-116 será bloqueada no domingo pela manhã por manifestantes da região"
    fontes = [
        {"url": "https://portal.test/carreata", "titulo": "Carreata", "trecho": nota},  # o próprio item
        {"url": "https://www.portal.test/amp/carreata", "titulo": "Carreata", "trecho": nota},  # mesmo domínio
        {"url": "https://outro.test/republica", "titulo": "Republicação", "trecho": nota + " (via agência)"},  # texto igual
        {"url": "https://oficial.test/nota", "titulo": "Nota da PRF", "trecho": "A PRF confirma o planejamento de desvio no km 210 e orienta motoristas"},
        {"url": "https://jornal.test/materia", "titulo": "Jornal", "trecho": "Moradores relatam cartazes convocando o ato para domingo às 9h"},
    ]
    r = agrupar_origens(fontes, url_item="https://portal.test/carreata")
    assert r["origens_distintas"] == 3 and r["corroboracoes"] == 2 and r["duplicadas"] == 2
    assert r["grupos"][0]["inclui_item"] and sorted(r["grupos"][0]["fontes"]) == [0, 1, 2]
    assert agrupar_origens([], None) == {"origens_distintas": 0, "corroboracoes": 0, "duplicadas": 0, "grupos": []}


def test_etiqueta_de_confianca_e_mecanica() -> None:
    from app.services.ia.verificacao import etiqueta_confianca

    assert etiqueta_confianca(5, "confirmado", None, houve_pesquisa=False)[0] == "nao_verificada"
    assert etiqueta_confianca(5, "falso", None, True)[0] == "refutada"
    assert etiqueta_confianca(2, "confirmado", None, True)[0] == "alta"
    assert etiqueta_confianca(1, "confirmado", None, True)[0] == "media"
    assert etiqueta_confianca(0, "confirmado", None, True)[0] == "baixa"
    assert etiqueta_confianca(3, "parcial", None, True)[0] == "media"  # resumo favorável não passa por cima do detalhe
    assert etiqueta_confianca(3, "nao_confirmado", None, True)[0] == "baixa"
    assert etiqueta_confianca(3, "confirmado", {"sustentadas": 4, "total": 4}, True)[0] == "alta"
    assert etiqueta_confianca(3, "confirmado", {"sustentadas": 3, "total": 4}, True)[0] == "media"
    etq, motivos = etiqueta_confianca(3, "confirmado", {"sustentadas": 1, "total": 4}, True)
    assert etq == "baixa" and any("aterramento fraco" in m for m in motivos)


def test_resumo_verificacao_e_aterramento_out() -> None:
    from app.services.ia.esquemas import AterramentoOut
    from app.services.ia.verificacao import resumo_verificacao, texto_etiqueta

    at = AterramentoOut.model_validate({"afirmacoes": [{"texto": "bloqueio domingo", "sustentada": "true", "fonte": 0}, {"texto": "km 210", "sustentada": "parcialmente"}, {"texto": "público de 5 mil", "sustentada": "não"}, "lixo"], "observacao": "x"})
    assert at.total == 3 and at.sustentadas == 1 and [a.sustentada for a in at.afirmacoes] == ["sim", "parcial", "nao"]
    pesquisa = {"verificacao": "confirmado", "fontes": [{"url": "https://oficial.test/nota", "trecho": "..."}, {"url": "https://jornal.test/m", "trecho": "..."}], "lacunas": "sem estimativa de público"}
    v = resumo_verificacao("https://portal.test/item", pesquisa, {"fontes": ["https://portal.test/item", "https://www.jornal.test/m2"]}, at.resumo())
    assert v["norma"] == "OOVS 0.1.0" and v["origens_distintas"] == 3 and v["corroboracoes"] == 2 and v["duplicadas"] == 1
    assert v["etiqueta"] == "baixa" and v["aterramento"] == {"sustentadas": 1, "total": 3} and any("lacunas" in m for m in v["motivos"])
    assert texto_etiqueta(v) == "confiança baixa · 3 origem(ns) distinta(s) · aterramento 1/3"
    v2 = resumo_verificacao("https://portal.test/item", None, {"fontes": ["https://portal.test/item"]}, None)
    assert v2["etiqueta"] == "nao_verificada" and v2["origens_distintas"] == 1 and v2["corroboracoes"] == 0 and texto_etiqueta(None) == ""
