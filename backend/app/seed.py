"""Templates extraídos literalmente do documento mestre O51NT (gerado em 02/10/2026)."""

from __future__ import annotations

import logging

from sqlmodel import Session, select

from app.models.radar import Fonte
from app.models.template import QueryTemplate

logger = logging.getLogger("o51nt.seed")

# (nome, categoria, descricao, query, placeholders)
TEMPLATES_PDF: list[tuple[str, str, str, str, list[str]]] = [
    # --- Dicas de pesquisa ---
    (
        "Redes sociais após data",
        "monitoramento_social",
        "Acompanhamento de assuntos nas principais Redes Sociais após determinada data.",
        '(site:facebook.com OR site:instagram.com OR site:x.com OR tiktok.com) (PRF OR "Polícia Rodoviária") '
        "(Eleições) after:2026-10-02",
        ["PRF", '"Polícia Rodoviária"', "Eleições", "2026-10-02"],
    ),
    (
        "Localidade após data",
        "localidade",
        "Acompanhamento de termos focado em localidades após determinada data. "
        "Obs: incluir nomes de localidades, cidades, bairros, nomes de rodovias, etc.",
        '(PRF OR "Polícia Rodoviária") (Bloqueio OR Blitz) (Votar OR Votação) (BR OR Rodovia OR Estrada) '
        "after:2026-10-01",
        ["2026-10-01"],
    ),
    (
        "Acompanhamento por Hashtags",
        "hashtags",
        "A partir de comentários em redes sociais identificar as hashtags que estão sendo marcadas.",
        "(site:facebook.com OR site:instagram.com) #NomeHashTag",
        ["#NomeHashTag"],
    ),
    (
        "Convites WhatsApp",
        "convites",
        "Localizar convites de grupos WhatsApp.",
        "(site:facebook.com OR site:instagram.com OR site:x.com OR site:tiktok.com) "
        '(chat.whatsapp.com "Termo a ser pesquisado")',
        ["Termo a ser pesquisado"],
    ),
    (
        "Convites Telegram",
        "convites",
        "Localizar convites de grupos Telegram.",
        "(site:facebook.com OR site:instagram.com OR site:x.com OR site:tiktok.com) "
        '(t.me/joinchat "Termo a ser pesquisado")',
        ["Termo a ser pesquisado"],
    ),
    # --- Operadores de precisão ---
    ("Frase exata", "precisao", "Frase exata, na ordem.", '"Polícia Rodoviária Federal"', []),
    ("Excluir termo", "precisao", "Excluir termo.", '"Policia Rodoviária Federal" -concurso', ["concurso"]),
    ("Alternativas (OR)", "precisao", "Alternativas.", 'PRF OR "Polícia Rodoviária"', []),
    (
        "Agrupamento lógico",
        "precisao",
        "Agrupamento lógico: (Termo1 OR Termo2).",
        '(PRF OR "Policia Rodoviária")',
        [],
    ),
    (
        "Curinga de palavras",
        "precisao",
        "Retorna resultados com os dois termos e qualquer palavra entre elas. "
        'Nota: o PDF traz ("Termo * Termo2) com aspas desbalanceadas; aqui corrigido.',
        '("Termo * Termo2")',
        ["Termo2", "Termo"],
    ),
    # --- Operadores temporais ---
    ("Antes da data (before)", "temporal", "Resultados contendo o termo PRF antes de 01/10/2026.", "PRF before:2026-10-01", ["PRF", "2026-10-01"]),
    ("Depois da data (after)", "temporal", "Resultados contendo o termo PRF depois de 01/10/2026.", "PRF after:2026-10-01", ["PRF", "2026-10-01"]),
    # --- Operadores de escopo ---
    ("Restringir domínio (site:)", "escopo", "Busca por termos apenas no site uol.", 'site:uol.com.br "Termo"', ["uol.com.br", "Termo"]),
    ("Excluir domínio (-site:)", "escopo", "Exclui a busca em sites gov.br.", "-site:gov.br", ["gov.br"]),
    ("Formato de arquivo (filetype:)", "escopo", "Restringe ao formato do arquivo.", 'filetype:pdf "termo"', ["pdf", "termo"]),
    ("Termo na URL (inurl:)", "escopo", "Pesquisa por termo dentro da URL.", "inurl:PRF", ["PRF"]),
    ("Termo no título (intitle:)", "escopo", "Pesquisa por termo dentro do título da página.", 'intitle:"Policia Rodoviária Federal"', []),
    ("Termo no corpo (intext:)", "escopo", "Restringe a pesquisa apenas no corpo textual da página.", 'intext:"Termo"', ["Termo"]),
]


# Strings de busca do boletim "Op. Eleições 2026" (02–05 OUT 2026): X/TweetDeck e TikTok.
# Categoria "x_tweetdeck" → o Query Builder as exibe com a etiqueta "Op. Eleições".
_OP = "Boletim Op. Eleições 2026 — "
TEMPLATES_OP_ELEICOES: list[tuple[str, str, str, str, list[str]]] = [
    (
        "X/TweetDeck — Imagem institucional PRF (AND)",
        "x_tweetdeck",
        _OP + "string TweetDeck de 02 e 03/OUT (seção Imagem institucional). O AND é explícito; "
        "no Google ele é implícito.",
        '(PRF OR "Polícia Rodoviária") AND (impedindo OR impedimento OR blitz OR eleitores)',
        [],
    ),
    (
        "X — Mobilidade em rodovias federais",
        "x_tweetdeck",
        _OP + "string de 04 e 05/OUT: impacto na mobilidade em rodovias federais. "
        "since: e -is:retweet são operadores do X; use o deeplink do X.",
        '(rodovia OR rodovias OR "BR-101" OR "BR-116" OR "BR-040" OR "BR-163" OR "BR-277" OR "BR-381" '
        'OR "BR 101" OR "BR 116" OR "BR 040") (bloqueio OR bloqueada OR bloqueado OR fechada OR interdição '
        "OR manifestação OR protesto OR trancaço OR paralisação OR carreata OR comboio OR blitz OR fiscalização "
        'OR congestionamento OR "trânsito parado") -is:retweet since:2026-10-04',
        ["2026-10-04"],
    ),
    (
        "X — Imagem institucional da PRF",
        "x_tweetdeck",
        _OP + "string de 04 e 05/OUT: monitoramento da imagem institucional da PRF no X. "
        "@PRFBrasil e #PRF são menção/hashtag do X.",
        '(PRF OR "Polícia Rodoviária Federal" OR @PRFBrasil OR #PRF) (blitz OR "blitz ilegal" OR eleitores '
        'OR "impedindo eleitores" OR "voto garantido" OR truculência OR "abuso de poder" OR orgulho OR parabéns '
        "OR atuação OR operação) -is:retweet since:2026-10-04",
        ["2026-10-04"],
    ),
    (
        "TikTok — Imagem institucional (termos)",
        "x_tweetdeck",
        _OP + "termos de 04/OUT para busca no TikTok, filtrando por relevância ou data de publicação "
        "(últimas 24 h). O TikTok ignora operadores: abra pelo deeplink TikTok e aplique os filtros lá.",
        '"blitz eleição" OR "blitz prf nordeste" OR "prf eleição"',
        [],
    ),
]


def seed_templates(session: Session) -> int:
    """Insere templates dos PDFs que ainda não existem (idempotente). Retorna quantos inseriu."""
    existentes = set(session.exec(select(QueryTemplate.nome)).all())
    novos = 0
    for nome, categoria, descricao, query, placeholders in TEMPLATES_PDF + TEMPLATES_OP_ELEICOES:
        if nome in existentes:
            continue
        session.add(
            QueryTemplate(
                nome=nome,
                categoria=categoria,
                descricao=descricao,
                query=query,
                placeholders="|".join(placeholders),
                origem_pdf=True,
            )
        )
        novos += 1
    session.commit()
    if novos:
        logger.info("templates do PDF seedados", extra={"dados": {"novos": novos}})
    return novos


# Feeds públicos verificados em 06/10/2026 (HTTP 200, XML válido, permitidos pelo robots.txt).
# (nome, url, categoria, ativa)
FONTES_PADRAO: list[tuple[str, str, str, bool]] = [
    ("Agência Brasil — últimas notícias", "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml", "oficial", True),
    ("Agência Brasil — política", "https://agenciabrasil.ebc.com.br/rss/politica/feed.xml", "oficial", True),
    ("g1 — geral", "https://g1.globo.com/rss/g1/", "imprensa", True),
    ("g1 — política", "https://g1.globo.com/rss/g1/politica/", "imprensa", True),
    ("Folha — Poder", "https://feeds.folha.uol.com.br/poder/rss091.xml", "imprensa", True),
    ("UOL — notícias", "https://rss.uol.com.br/feed/noticias.xml", "imprensa", True),
    ("Metrópoles", "https://www.metropoles.com/feed", "imprensa", True),
    ("Poder360", "https://www.poder360.com.br/feed/", "imprensa", True),
    ("CNN Brasil", "https://www.cnnbrasil.com.br/feed/", "imprensa", True),
    ("Estadão — política", "https://www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/politica/?outputType=xml", "imprensa", True),
    ("Mastodon — #eleicoes2026 (mastodon.social)", "https://mastodon.social/tags/eleicoes2026.rss", "rede", True),
    # --- validadas ao vivo em 2026-10-10 (backend/scripts/validar_fontes.py no GitHub Actions; itens recentes, robots OK) ---
    ("Google Notícias — busca: manifestação/protesto/bloqueio/carreata", "https://news.google.com/rss/search?q=manifesta%C3%A7%C3%A3o%20OR%20manifestantes%20OR%20protesto%20OR%20bloqueio%20OR%20carreata&hl=pt-BR&gl=BR&ceid=BR:pt-419", "busca", True),
    ("Agência Lupa", "https://lupa.uol.com.br/feed", "checagem", True),
    ("Aos Fatos", "https://www.aosfatos.org/noticias/feed/", "checagem", True),
    ("TSE — notícias", "https://www.tse.jus.br/comunicacao/noticias/rss", "oficial", True),
    ("Agência Pública", "https://apublica.org/feed/", "independente", True),
    ("The Intercept Brasil", "https://www.intercept.com.br/feed/", "independente", True),
    ("Nexo Jornal", "https://www.nexojornal.com.br/rss.xml", "independente", True),
    ("CartaCapital", "https://www.cartacapital.com.br/feed/", "independente", True),
    ("Revista Fórum", "https://revistaforum.com.br/rss", "independente", True),
    ("Brasil 247", "https://www.brasil247.com/feed", "independente", True),
    ("Jornal GGN", "https://jornalggn.com.br/feed/", "independente", True),
    ("Diário do Centro do Mundo", "https://www.diariodocentrodomundo.com.br/feed/", "independente", True),
    ("Mídia Ninja", "https://midianinja.org/feed/", "independente", True),
    ("Ponte Jornalismo", "https://ponte.org/feed/", "independente", True),
    ("piauí", "https://piaui.folha.uol.com.br/feed/", "independente", True),
    ("JOTA", "https://www.jota.info/feed", "independente", True),
    ("BBC News Brasil", "https://feeds.bbci.co.uk/portuguese/rss.xml", "internacional", True),
    ("RFI Brasil", "https://www.rfi.fr/br/rss", "internacional", True),
    ("Mastodon — #manifestacao (mastodon.social)", "https://mastodon.social/tags/manifestacao.rss", "rede", True),
    ("A Gazeta (ES)", "https://www.agazeta.com.br/rss", "regional", True),
    ("A Tarde (BA)", "https://atarde.com.br/rss", "regional", True),
    ("Agora RN (RN)", "https://agorarn.com.br/feed/", "regional", True),
    ("Tribuna do Norte (RN)", "https://tribunadonorte.com.br/feed", "regional", True),
    ("Bem Paraná (PR)", "https://www.bemparana.com.br/feed/", "regional", True),
    ("Tribuna PR (PR)", "https://www.tribunapr.com.br/feed/", "regional", True),
    ("Cidade Verde (PI)", "https://cidadeverde.com/rss", "regional", True),
    ("Conexão Tocantins (TO)", "https://conexaoto.com.br/feed", "regional", True),
    ("DOL (PA)", "https://dol.com.br/rss", "regional", True),
    ("Diário do Amapá (AP)", "https://www.diariodoamapa.com.br/feed/", "regional", True),
    ("Folha de Boa Vista (RR)", "https://folhabv.com.br/feed/", "regional", True),
    ("Gazeta de Alagoas (AL)", "https://www.gazetaweb.com/rss", "regional", True),
    ("Imirante (MA)", "https://imirante.com/rss", "regional", True),
    ("O Imparcial (MA)", "https://oimparcial.com.br/feed/", "regional", True),
    ("Infonet (SE)", "https://infonet.com.br/feed/", "regional", True),
    ("Jornal da Paraíba (PB)", "https://www.jornaldaparaiba.com.br/feed", "regional", True),
    ("Marco Zero Conteúdo (PE)", "https://marcozero.org/feed/", "regional", True),
    ("ND Mais (SC)", "https://ndmais.com.br/feed/", "regional", True),
    ("ac24horas (AC)", "https://ac24horas.com/feed/", "regional", True),
    # --- 2ª rodada (19:16 UTC): feeds descobertos na página inicial, feeds com robots.txt restritivo e páginas sem RSS ---
    ("O Globo", "https://oglobo.globo.com/rss/oglobo", "imprensa", True),
    ("Brasil de Fato", "https://www.brasildefato.com.br/feed/", "independente", True),
    ("O Antagonista", "https://oantagonista.com.br/feed/", "independente", True),
    ("Agência Senado", "https://www12.senado.leg.br/noticias/RSS", "oficial", True),
    ("MJSP — notícias (gov.br)", "https://www.gov.br/mj/RSS", "oficial", True),
    ("Reddit — r/brasil (novos)", "https://www.reddit.com/r/brasil/new/.rss", "rede", True),
    ("Campo Grande News (MS)", "https://www.campograndenews.com.br/rss", "regional", True),
    ("Bahia Notícias (BA)", "https://www.bahianoticias.com.br/principal/rss.xml", "regional", True),
    ("Jornal do Comércio (RS)", "https://www.jornaldocomercio.com/_conteudo/home/rss.xml", "regional", True),
    ("O Dia (RJ)", "https://odia.ig.com.br/_conteudo/ultimas-noticias/rss.xml", "regional", True),
    ("Agência Câmara (página)", "https://www.camara.leg.br/noticias/", "oficial", True),
    ("Correio Braziliense (DF, página)", "https://www.correiobraziliense.com.br/", "regional", True),
    ("Correio do Povo (RS, página)", "https://www.correiodopovo.com.br/", "regional", True),
    ("Diário do Nordeste (CE, página)", "https://diariodonordeste.verdesmares.com.br/", "regional", True),
    ("O Povo (CE, página)", "https://www.opovo.com.br/", "regional", True),
    ("Estado de Minas (MG, página)", "https://www.em.com.br/", "regional", True),
    ("O Tempo (MG, página)", "https://www.otempo.com.br/", "regional", True),
    ("Gazeta do Povo (PR, página)", "https://www.gazetadopovo.com.br/", "regional", True),
    ("Gazeta Digital (MT, página)", "https://www.gazetadigital.com.br/", "regional", True),
    ("Meio Norte (PI, página)", "https://www.meionorte.com/", "regional", True),
    ("Tribuna Hoje (AL, página)", "https://tribunahoje.com/", "regional", True),
    ("A Crítica (AM, página)", "https://www.acritica.com/", "regional", True),
    ("Correio do Estado (MS, página)", "https://correiodoestado.com.br/", "regional", True),
    ("R7 — notícias (página)", "https://noticias.r7.com/", "imprensa", True),
]
# Semeadas com respeitar_robots=False (decisão do dono, 2026-10-10): o robots.txt do host não libera a coleta automática,
# mas o feed existe para ser lido por máquina. Tudo o mais respeita o robots.txt.
FONTES_PADRAO_SEM_ROBOTS: frozenset[str] = frozenset({u for _n, u, c, _a in FONTES_PADRAO if c == "busca"} | {"https://oglobo.globo.com/rss/oglobo", "https://oantagonista.com.br/feed/", "https://www.reddit.com/r/brasil/new/.rss"})
# Sites sem RSS utilizável: o Radar extrai os links de matéria da página (tipo "pagina", verificados a cada 30 min).
FONTES_PADRAO_PAGINA: frozenset[str] = frozenset({u for n, u, _c, _a in FONTES_PADRAO if "página)" in n})

# Catálogo exibido na tela (as acima + modelos que dependem de dados do analista).
CATALOGO_FONTES: list[dict] = [
    *({"nome": n, "url": u, "categoria": c, "tipo": "pagina" if u in FONTES_PADRAO_PAGINA else "feed", "descricao": "Página de notícias sem RSS (links de matéria extraídos pelo Radar)." if u in FONTES_PADRAO_PAGINA else "Feed público validado ao vivo."} for n, u, c, _a in FONTES_PADRAO),
    {
        "nome": "Google Alertas (feed pessoal)",
        "url": "https://www.google.com/alerts",
        "categoria": "alerta",
        "tipo": "modelo",
        "descricao": "Crie o alerta em google.com/alerts com o termo desejado, escolha 'Entregar em: Feed RSS' e cole aqui a URL do feed "
        "(https://www.google.com/alerts/feeds/...). É a busca do Google entregue pelo próprio Google para leitores de feed. "
        "O robots.txt do google.com não cobre feeds pessoais: marque 'ignorar robots.txt' só para esta fonte.",
    },
    {
        "nome": "Mastodon — hashtag (qualquer instância)",
        "url": "https://mastodon.social/tags/{hashtag}.rss",
        "categoria": "rede",
        "tipo": "modelo",
        "descricao": "Troque {hashtag} pela hashtag sem '#' (ex.: brasil2026) e, se quiser, a instância.",
    },
    # Modelos por busca/canal (2026-10-10). O robots.txt desses hosts não libera a coleta automática; a decisão de usar
    # a opção "ignorar robots.txt" é do analista, fonte a fonte (nunca há burla de CAPTCHA, login ou bloqueio).
    {
        "nome": "Google Notícias — busca (RSS por termo)",
        "url": "https://news.google.com/rss/search?q={termos}&hl=pt-BR&gl=BR&ceid=BR:pt-419",
        "categoria": "busca",
        "tipo": "modelo",
        "descricao": "Troque {termos} pela busca (ex.: manifesta%C3%A7%C3%A3o%20OR%20manifestantes). Feed de resultados do Google Notícias; "
        "marque 'ignorar robots.txt' nesta fonte.",
    },
    {
        "nome": "YouTube — canal (feed de vídeos)",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
        "categoria": "rede",
        "tipo": "modelo",
        "descricao": "Troque {channel_id} pelo ID do canal (começa com UC…; está em 'Compartilhar canal' ou no código da página). "
        "Marque 'ignorar robots.txt' nesta fonte.",
    },
    {
        "nome": "Reddit — subreddit (novos)",
        "url": "https://www.reddit.com/r/{subreddit}/new/.rss",
        "categoria": "rede",
        "tipo": "modelo",
        "descricao": "Troque {subreddit} pelo nome da comunidade (ex.: brasil).",
    },
]


def seed_fontes(session: Session) -> int:
    """Insere as fontes padrão que ainda não existem (idempotente; não reativa fontes desativadas pelo analista)."""
    existentes = set(session.exec(select(Fonte.url)).all())
    novos = 0
    for nome, url, categoria, ativa in FONTES_PADRAO:
        if url in existentes:
            continue
        pagina = url in FONTES_PADRAO_PAGINA
        session.add(Fonte(nome=nome, url=url, categoria=categoria, ativa=ativa, respeitar_robots=url not in FONTES_PADRAO_SEM_ROBOTS, tipo="pagina" if pagina else "feed", intervalo_min=30 if pagina else None))
        novos += 1
    session.commit()
    if novos:
        logger.info("fontes do radar seedadas", extra={"dados": {"novas": novos}})
    return novos
