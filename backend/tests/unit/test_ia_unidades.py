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
    assert estimar_custo("claude-haiku-5-5", 1_000_000, 0) == 1.0
    assert estimar_custo("anthropic/claude-sonnet-5-5", 0, 1_000_000) == 15.0
    assert estimar_custo("desconhecido", 1_000_000, 0) == 3.0


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
