"""Hub de ferramentas externas — catálogo extraído do documento mestre O51NT."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote_plus

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/tools", tags=["tools"])


class Ferramenta(BaseModel):
    id: str
    nome: str
    url: str
    categoria: str
    tags: list[str]
    descricao: str
    deeplink: str | None = None  # template com {q}
    tipo_parametro: Literal["texto", "url_imagem", "hashtag"] | None = None


CATALOGO: list[Ferramenta] = [
    # Twitter - X
    Ferramenta(
        id="oldtweetdeck", nome="TweetDeck (OldTweetDeck)", url="https://github.com/dimdenGD/OldTweetDeck/",
        categoria="Twitter - X", tags=["tempo real", "extensão"], descricao="TweetDeck - Acompanhamento em tempo real.",
    ),
    Ferramenta(
        id="onemilliontweetmap", nome="The one million tweet map", url="https://onemilliontweetmap.com/",
        categoria="Twitter - X", tags=["hashtags", "mapa"], descricao="[HashTags] The one million tweet map.",
    ),
    Ferramenta(
        id="trends24", nome="trends24 — Brazil", url="https://trends24.in/brazil/",
        categoria="Twitter - X", tags=["hashtags", "trending"],
        descricao="Brazil — X (Twitter) trending topics and hashtags today.",
    ),
    # Facebook
    Ferramenta(
        id="whopostedwhat", nome="Who posted what?", url="https://whopostedwhat.com/",
        categoria="Facebook", tags=["busca", "posts"], descricao="Who posted what?",
    ),
    Ferramenta(
        id="sowsearch", nome="Facebook Search (sowsearch)", url="https://sowsearch.info/",
        categoria="Facebook", tags=["busca"], descricao="Facebook Search.",
    ),
    # Busca por Imagens
    Ferramenta(
        id="google_images", nome="Imagens do Google", url="https://www.google.com/imghp",
        categoria="Busca por Imagens", tags=["imagem", "reversa"], descricao="Imagens do Google.",
        deeplink="https://www.google.com/search?tbm=isch&q={q}", tipo_parametro="texto",
    ),
    Ferramenta(
        id="tineye", nome="TinEye", url="https://tineye.com/",
        categoria="Busca por Imagens", tags=["imagem", "reversa"], descricao="TinEye — busca reversa de imagens.",
        deeplink="https://tineye.com/search?url={q}", tipo_parametro="url_imagem",
    ),
    Ferramenta(
        id="yandex_images", nome="Yandex.Images", url="https://yandex.com/images",
        categoria="Busca por Imagens", tags=["imagem", "reversa"],
        descricao="Yandex.Images: search for images on the internet, search by image.",
        deeplink="https://yandex.com/images/search?text={q}", tipo_parametro="texto",
    ),
    Ferramenta(
        id="sensity", nome="Deep Fake Detection (Sensity)", url="https://platform.sensity.ai/login",
        categoria="Busca por Imagens", tags=["deepfake", "login"], descricao="Deep Fake Detection (requer conta própria).",
    ),
    Ferramenta(
        id="lenso", nome="Lenso.ai", url="https://lenso.ai/pt",
        categoria="Busca por Imagens", tags=["imagem", "reversa", "rostos"], descricao="Lenso.ai: Pt.",
    ),
    Ferramenta(
        id="search_by_image", nome="[Extensão] Search by Image",
        url="https://chromewebstore.google.com/detail/search-by-image/cnojnbdhbhnkbcieeekonklommdnndci",
        categoria="Busca por Imagens", tags=["extensão", "imagem"], descricao="[Extensão Navegador] Search by Image.",
    ),
    # Ferramentas
    Ferramenta(
        id="commentpicker", nome="Comment Picker", url="https://commentpicker.com/",
        categoria="Ferramentas", tags=["comentários"], descricao="Comment Picker.",
    ),
    Ferramenta(
        id="evidence_collector", nome="[Extensão] Evidence Collector",
        url="https://chromewebstore.google.com/detail/evidence-collector/mkloikhcnmoebenehakgkccipondapdk",
        categoria="Ferramentas", tags=["extensão", "evidências"], descricao="[Extensão Navegador] Evidence Collector.",
    ),
    Ferramenta(
        id="google_alerts", nome="Alertas do Google", url="https://www.google.com.br/alerts",
        categoria="Ferramentas", tags=["monitoramento", "alertas"],
        descricao="Alertas do Google. Monitorar a Web para ver conteúdo novo e interessante.",
    ),
    Ferramenta(
        id="programmable_search", nome="Programmable Search Engine", url="https://programmablesearchengine.google.com/about/",
        categoria="Ferramentas", tags=["busca"], descricao="Programmable Search Engine by Google.",
    ),
    Ferramenta(
        id="google_trends", nome="Em alta – Google Trends", url="https://trends.google.com.br/trending",
        categoria="Ferramentas", tags=["tendências"], descricao="Em alta – Google Trends.",
        deeplink="https://trends.google.com.br/trends/explore?geo=BR&q={q}", tipo_parametro="texto",
    ),
    # ------------------------------------------------------------------ Checagem de fatos
    # Seção "Fake news" do boletim Op. Eleições 2026 (o boletim cita AFP Checamos e Projeto Comprova).
    Ferramenta(
        id="afp_checamos", nome="AFP Checamos", url="https://checamos.afp.com/",
        categoria="Checagem de fatos", tags=["fake news", "checagem"],
        descricao="Serviço de checagem da AFP. O site divulga o canal de WhatsApp para enviar conteúdo suspeito.",
    ),
    Ferramenta(
        id="comprova", nome="Projeto Comprova", url="https://projetocomprova.com.br/",
        categoria="Checagem de fatos", tags=["fake news", "checagem", "eleições"],
        descricao="Coalizão de veículos que verifica conteúdos sobre eleições e políticas públicas.",
        deeplink="https://projetocomprova.com.br/?s={q}", tipo_parametro="texto",
    ),
    Ferramenta(
        id="lupa", nome="Agência Lupa", url="https://lupa.uol.com.br/",
        categoria="Checagem de fatos", tags=["fake news", "checagem"], descricao="Agência de checagem de fatos.",
    ),
    Ferramenta(
        id="aos_fatos", nome="Aos Fatos", url="https://www.aosfatos.org/",
        categoria="Checagem de fatos", tags=["fake news", "checagem"], descricao="Agência de checagem de fatos.",
    ),
    Ferramenta(
        id="fato_ou_fake", nome="Fato ou Fake (g1)", url="https://g1.globo.com/fato-ou-fake/",
        categoria="Checagem de fatos", tags=["fake news", "checagem"], descricao="Checagem do g1 (busca geral do g1 pré-preenchida).",
        deeplink="https://g1.globo.com/busca/?q={q}", tipo_parametro="texto",
    ),
    Ferramenta(
        id="boatos", nome="Boatos.org", url="https://www.boatos.org/",
        categoria="Checagem de fatos", tags=["fake news", "boatos"], descricao="Desmentidos de boatos que circulam em redes e WhatsApp.",
        deeplink="https://www.boatos.org/?s={q}", tipo_parametro="texto",
    ),
    Ferramenta(
        id="estadao_verifica", nome="Estadão Verifica", url="https://www.estadao.com.br/estadao-verifica/",
        categoria="Checagem de fatos", tags=["fake news", "checagem"], descricao="Núcleo de checagem do Estadão.",
    ),
    Ferramenta(
        id="tse_fato_ou_boato", nome="TSE — Fato ou Boato", url="https://www.justicaeleitoral.jus.br/fato-ou-boato/",
        categoria="Checagem de fatos", tags=["fake news", "eleições", "oficial"],
        descricao="Página oficial da Justiça Eleitoral com desinformação já desmentida.",
    ),
    Ferramenta(
        id="google_factcheck", nome="Google Fact Check Explorer", url="https://toolbox.google.com/factcheck/explorer",
        categoria="Checagem de fatos", tags=["fake news", "busca"],
        descricao="Busca em checagens publicadas por agências do mundo todo (ClaimReview).",
        deeplink="https://toolbox.google.com/factcheck/explorer/search/{q};hl=pt", tipo_parametro="texto",
    ),
    # ------------------------------------------------------------------ Busca em redes
    # Seção "Imagem institucional" do boletim: strings no X/TweetDeck e termos no TikTok.
    Ferramenta(
        id="x_search", nome="Busca no X (recentes)", url="https://x.com/explore",
        categoria="Busca em redes", tags=["x", "twitter", "tempo real"],
        descricao="Busca do X ordenada por mais recentes — o mesmo que uma coluna do TweetDeck. Aceita since:, -is:retweet, from:…",
        deeplink="https://x.com/search?q={q}&src=typed_query&f=live", tipo_parametro="texto",
    ),
    Ferramenta(
        id="tiktok_search", nome="Busca no TikTok", url="https://www.tiktok.com/search",
        categoria="Busca em redes", tags=["tiktok", "vídeo"],
        descricao="Busca no TikTok. Aplique lá os filtros de relevância ou data de publicação (últimas 24 h), como no boletim.",
        deeplink="https://www.tiktok.com/search?q={q}", tipo_parametro="texto",
    ),
    Ferramenta(
        id="instagram_tag", nome="Instagram — hashtag", url="https://www.instagram.com/explore/tags/",
        categoria="Busca em redes", tags=["instagram", "hashtag"],
        descricao="Página pública da hashtag no Instagram (informe a hashtag, com ou sem #).",
        deeplink="https://www.instagram.com/explore/tags/{q}/", tipo_parametro="hashtag",
    ),
    Ferramenta(
        id="youtube_search", nome="Busca no YouTube", url="https://www.youtube.com/",
        categoria="Busca em redes", tags=["youtube", "vídeo"], descricao="Busca no YouTube (vídeos, lives e canais).",
        deeplink="https://www.youtube.com/results?search_query={q}", tipo_parametro="texto",
    ),
    Ferramenta(
        id="facebook_search", nome="Busca no Facebook", url="https://www.facebook.com/search/top/",
        categoria="Busca em redes", tags=["facebook"],
        descricao="Busca do Facebook (exige sessão no navegador do analista; o app não faz login).",
        deeplink="https://www.facebook.com/search/top/?q={q}", tipo_parametro="texto",
    ),
    Ferramenta(
        id="google_news", nome="Google Notícias", url="https://news.google.com/?hl=pt-BR&gl=BR&ceid=BR:pt-419",
        categoria="Busca em redes", tags=["notícias", "imprensa"],
        descricao="Busca de notícias (seção 'Notícias relevantes' do boletim). Coleta automática não é permitida pelo robots.txt; use o deeplink.",
        deeplink="https://news.google.com/search?q={q}&hl=pt-BR&gl=BR&ceid=BR%3Apt-419", tipo_parametro="texto",
    ),
]

_POR_ID = {f.id: f for f in CATALOGO}


def montar_deeplink(ferramenta: Ferramenta, q: str | None) -> str:
    if ferramenta.deeplink and q and q.strip():
        valor = q.strip()
        if ferramenta.tipo_parametro == "hashtag":  # #Eleicoes2026 → Eleicoes2026 (sem '#' nem espaços)
            valor = valor.lstrip("#").replace(" ", "")
            if not valor:
                return ferramenta.url
        return ferramenta.deeplink.format(q=quote_plus(valor))
    return ferramenta.url


@router.get("", response_model=list[Ferramenta])
async def listar(categoria: str | None = None) -> list[Ferramenta]:
    return [f for f in CATALOGO if categoria is None or f.categoria == categoria]


@router.get("/deeplink")
async def deeplink(tool: str, q: str | None = Query(default=None, max_length=2000)) -> dict:
    f = _POR_ID.get(tool)
    if f is None:
        raise HTTPException(404, "Ferramenta não encontrada")
    url = montar_deeplink(f, q)
    return {"tool": f.id, "url": url, "prefill": url != f.url}
