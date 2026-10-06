from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app import db
from app.models.monitor import Monitor
from app.models.radar import Fonte, FonteItem, MonitorHit
from app.services import radar
from app.services.scraper import EthicalScraper, MemoryBackoffStore
from tests.conftest import FakeFetcher

pytestmark = pytest.mark.unit

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel><title>Feed Teste</title>
<item><title><![CDATA[PRF reforça policiamento nas rodovias para as eleições]]></title><link>https://ex.org/n1</link>
<description><![CDATA[<p>A Polícia Rodoviária Federal anunciou <b>blitz</b> em BRs no domingo.</p>]]></description>
<pubDate>Mon, 05 Oct 2026 10:00:00 -0300</pubDate><guid>n1</guid></item>
<item><title>Concurso da PRF abre inscrições</title><link>https://ex.org/n2</link><description>Edital publicado.</description>
<pubDate>Sun, 04 Oct 2026 08:00:00 GMT</pubDate></item>
<item><title>Sem link</title><description>x</description></item>
<item><title>Repetido</title><link>https://ex.org/n1</link></item>
</channel></rss>"""

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom</title>
<entry><title>Carreata interdita a BR-116 em Americana</title><link rel="self" href="https://ex.org/self"/><link rel="alternate" href="https://ex.org/a1"/>
<summary type="html">&lt;p&gt;Trânsito parado por duas horas.&lt;/p&gt;</summary><updated>2026-10-06T12:30:00Z</updated></entry>
<entry><link href="https://ex.org/a2"/><content type="html">&lt;p&gt;Post do #Eleicoes2026 sem título&lt;/p&gt;</content><published>2026-10-06T13:00:00-03:00</published></entry>
</feed>"""


# ---------------------------------------------------------------- parse
def test_parse_rss_limpa_html_datas_e_duplicatas() -> None:
    itens = radar.parse_feed(RSS)
    assert [i.url for i in itens] == ["https://ex.org/n1", "https://ex.org/n2"]
    assert itens[0].titulo == "PRF reforça policiamento nas rodovias para as eleições"
    assert itens[0].resumo == "A Polícia Rodoviária Federal anunciou blitz em BRs no domingo."
    assert itens[0].publicado_em == datetime(2026, 10, 5, 13, 0, tzinfo=UTC)
    assert itens[1].publicado_em == datetime(2026, 10, 4, 8, 0, tzinfo=UTC)


def test_parse_atom_link_alternate_e_titulo_fallback() -> None:
    itens = radar.parse_feed(ATOM)
    assert itens[0].url == "https://ex.org/a1" and itens[0].resumo == "Trânsito parado por duas horas."
    assert itens[0].publicado_em == datetime(2026, 10, 6, 12, 30, tzinfo=UTC)
    assert itens[1].titulo == "Post do #Eleicoes2026 sem título"  # Mastodon: sem <title>
    assert itens[1].publicado_em == datetime(2026, 10, 6, 16, 0, tzinfo=UTC)


@pytest.mark.parametrize("texto", ["<html><body>não é feed</body></html>", "<rss><channel><item><title>x</title></item>", ""])
def test_parse_feed_invalido(texto: str) -> None:
    with pytest.raises(ValueError):
        radar.parse_feed(texto)


# ---------------------------------------------------------------- matcher
N1 = radar.alvo_de("PRF reforça policiamento nas rodovias para as eleições", "A Polícia Rodoviária Federal anunciou blitz em BRs.", "https://ex.org/n1", datetime(2026, 10, 5, 13, tzinfo=UTC))
N2 = radar.alvo_de("Concurso da PRF abre inscrições", "Edital publicado.", "https://ex.org/n2", datetime(2026, 10, 4, 8, tzinfo=UTC))
SEM_DATA = radar.alvo_de("PRF blitz", "", "https://x.com/post/1", None)


def casa(q: str, alvo: radar.Alvo, modo: str = "termos") -> list[str]:
    return radar.compilar(q, modo).casar(alvo)


def test_and_implicito_e_explicito() -> None:
    assert casa("PRF blitz", N1) == ["PRF", "blitz"]
    assert casa("PRF AND blitz", N1) == ["PRF", "blitz"]
    assert casa("PRF blitz", N2) == []


def test_or_parenteses_acentos_e_caixa() -> None:
    termos = casa('(PRF OR "Polícia Rodoviária") (ELEICOES)', N1)
    assert "PRF" in termos and '"Polícia Rodoviária"' in termos and "ELEICOES" in termos
    assert casa("(PRF OR PF) (concurso OR edital)", N2) == ["PRF", "concurso", "edital"]


def test_frase_exata_com_curinga_e_negacao() -> None:
    assert casa('"Polícia * Federal"', N1) == ['"Polícia * Federal"']
    assert casa('"Rodoviária Federal anunciou"', N1) and not casa('"Federal Rodoviária"', N1)
    assert casa("PRF -concurso", N1) == ["PRF"] and casa("PRF -concurso", N2) == []


def test_hashtag_e_mencao_com_ou_sem_simbolo() -> None:
    a = radar.alvo_de("Mobilização", "veja #EleNão hoje e @PRFBrasil", "https://ex.org/h", None)
    assert casa("#elenao", a) == ["#elenao"] and casa("@prfbrasil", a) == ["@prfbrasil"]
    b = radar.alvo_de("EleNão protesto", "", "https://ex.org/h2", None)
    assert casa("#EleNão", b) == ["#EleNão"]
    assert casa("#EleNão", radar.alvo_de("elenaox", "", "https://ex.org/h3", None)) == []


def test_site_modo_termos_vs_estrito() -> None:
    assert casa("site:x.com PRF", N1) == ["PRF"]  # termos: domínio ignorado
    assert casa("site:x.com PRF", N1, "estrito") == []
    assert casa("site:x.com PRF", SEM_DATA, "estrito") == ["PRF"]
    assert casa("-site:ex.org PRF", N1, "estrito") == [] and casa("-site:ex.org PRF", SEM_DATA, "estrito") == ["PRF"]
    assert casa("(site:facebook.com OR site:instagram.com OR tiktok.com) PRF", N1) == ["PRF"]


def test_janelas_temporais_google_e_x() -> None:
    # N1 = 05/10, N2 = 04/10. after:/before:/since: inclusivos; until: exclusivo
    assert casa("PRF after:2026-10-05", N1) and not casa("PRF after:2026-10-05", N2)
    assert casa("PRF after:2026-10-04", N2)  # inclusivo: a data do próprio dia entra
    assert casa("PRF since:2026-10-04", N2) and not casa("PRF until:2026-10-04", N2)
    assert casa("PRF before:2026-10-04", N2) and not casa("PRF before:2026-10-04", N1)
    assert casa("PRF after:2026-10-04", SEM_DATA)  # sem data não restringe


def test_url_mastodon_tag_e_fonte_automatica(data_dir: Path) -> None:
    assert radar.url_mastodon_tag("#EleNão") == "https://mastodon.social/tags/EleN%C3%A3o.rss"
    assert radar.url_mastodon_tag("Eleicoes 2026", "masto.pt") == "https://masto.pt/tags/Eleicoes2026.rss"
    db.init_db()
    with Session(db.get_engine()) as s:
        f1 = radar.garantir_fonte_hashtag(s, "#EleNão")
        f2 = radar.garantir_fonte_hashtag(s, "EleNão")
        assert f1.id == f2.id and f1.nome == "Mastodon — #EleNão (auto)" and f1.categoria == "rede" and f1.ativa
        s.add(Monitor(nome="h", query="#Brasil2026", tipo="hashtag"))
        s.add(Monitor(nome="q", query="PRF", tipo="query"))
        s.commit()
        assert radar.sincronizar_fontes_hashtags(s) == 1
        assert radar.sincronizar_fontes_hashtags(s) == 0


def test_intitle_inurl_intext_filetype() -> None:
    assert casa("intitle:concurso PRF", N2) and not casa("intitle:concurso PRF", N1)
    assert casa("inurl:n2 PRF", N2) and not casa("inurl:n2 PRF", N1)
    assert casa("intext:blitz PRF", N1) and not casa("intext:blitz PRF", N2)
    assert not casa("filetype:pdf PRF", N1)


def test_query_sem_termos_nao_casa_nada() -> None:
    m = radar.compilar("site:x.com after:2026-01-01 -is:retweet")
    assert not m.tem_termos and m.casar(SEM_DATA) == []
    assert radar.compilar("-concurso").tem_termos is False


def test_template_redes_sociais_do_pdf_casa_noticia() -> None:
    q = '(site:facebook.com OR site:instagram.com OR site:x.com OR tiktok.com) (PRF OR "Polícia Rodoviária") (Eleições) after:2026-10-02'
    assert set(casa(q, N1)) >= {"PRF", "Eleições"}
    assert casa(q, N1, "estrito") == []


def test_operadores_de_motor_nao_restringem() -> None:
    assert casa("PRF -is:retweet lang:pt min_faves:10 has:media from:PRFBrasil", N1) == ["PRF"]


# ---------------------------------------------------------------- ciclo
def _fetcher() -> FakeFetcher:
    return FakeFetcher({"https://feeds.test/a.xml": (200, RSS), "https://feeds.test/c.xml": (200, ATOM), "https://feeds.test/b.xml": (404, "nope")})


async def test_ciclo_atualiza_fontes_casa_monitores_alerta_e_deduplica(data_dir: Path) -> None:
    db.init_db()
    f = _fetcher()
    scraper = EthicalScraper(intervalo=0, fetcher_estatico=f, fetcher_js=f, backoff=MemoryBackoffStore())
    with Session(db.get_engine()) as s:
        for nome, url in (("A", "https://feeds.test/a.xml"), ("B", "https://feeds.test/b.xml"), ("C", "https://feeds.test/c.xml")):
            s.add(Fonte(nome=nome, url=url))
        s.add(Fonte(nome="inativa", url="https://feeds.test/x.xml", ativa=False))
        m1 = Monitor(nome="blitz", query="PRF blitz")
        m2 = Monitor(nome="tag", query="#Eleicoes2026", tipo="hashtag")
        m3 = Monitor(nome="sem termos", query="site:x.com")
        m4 = Monitor(nome="pausado", query="PRF", ativo=False)
        s.add_all([m1, m2, m3, m4])
        s.commit()
        r = await radar.ciclo(s, scraper)
        assert r["itens_novos"] == 4 and r["monitores_avaliados"] == 3
        assert r["hits_por_monitor"] == {str(m1.id): 1, str(m2.id): 1} and r["alertas"] == 2
        por_nome = {x["nome"]: x for x in r["fontes"]}
        assert por_nome["A"]["novos"] == 2 and por_nome["B"]["status"] == 404 and por_nome["B"]["erro"] and "inativa" not in por_nome
        fb = s.exec(select(Fonte).where(Fonte.nome == "B")).one()
        assert fb.ultimo_status == 404 and fb.ultimo_erro and fb.itens_total == 0
        fa = s.exec(select(Fonte).where(Fonte.nome == "A")).one()
        assert fa.itens_total == 2 and fa.novos_ultima == 2 and fa.ultima_coleta is not None
        hit = s.exec(select(MonitorHit).where(MonitorHit.monitor_id == m1.id)).one()
        assert hit.url == "https://ex.org/n1" and hit.termos == "PRF | blitz" and hit.fonte_nome == "A" and hit.origem == "radar"
        assert not any("https://feeds.test/x.xml" in u for u in f.chamadas)
        # alerta JSONL com os hits
        linhas = [json.loads(l) for p in (data_dir / "alerts").glob("*.jsonl") for l in p.read_text().splitlines()]
        assert [e["tipo"] for e in linhas] == ["radar", "radar"] and linhas[0]["hits"][0]["url"]
        # segundo ciclo: nada novo, nada repetido
        r2 = await radar.ciclo(s, scraper)
        assert r2["itens_novos"] == 0 and r2["hits_novos"] == 0
        assert s.exec(select(FonteItem)).all().__len__() == 4
    await scraper.stop()


async def test_casar_monitor_cache_novo_monitor(data_dir: Path) -> None:
    db.init_db()
    f = _fetcher()
    scraper = EthicalScraper(intervalo=0, fetcher_estatico=f, fetcher_js=f, backoff=MemoryBackoffStore())
    with Session(db.get_engine()) as s:
        s.add(Fonte(nome="C", url="https://feeds.test/c.xml"))
        s.commit()
        await radar.ciclo(s, scraper)
        mon = Monitor(nome="carreata", query="carreata OR motociata")
        s.add(mon)
        s.commit()
        novos = radar.casar_monitor_cache(s, mon)
        assert [h.url for h in novos] == ["https://ex.org/a1"] and novos[0].origem == "execucao"
        assert radar.casar_monitor_cache(s, mon) == []  # idempotente
        assert radar.contagens_hits(s) == {mon.id: (1, 1)}
    await scraper.stop()
