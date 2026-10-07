"""Resolve uma URL colada pelo analista em uma `Entrada` para o Analisador.

- imagem direta (content-type image/*) → bytes
- post do Bluesky (bsky.app/profile/…/post/…) → API pública: texto + alt + 1ª imagem
- página genérica (t.me/<canal>/<id>?embed=1, notícia, Mastodon…) → og:image/twitter:image + og:title/og:description
- X: sem página pública sem JS; tenta o oEmbed público só para o texto (imagem via print)
Tudo passa pelo EthicalScraper (robots, rate limit, backoff).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote, urljoin, urlsplit

from app.services.convocacoes import bluesky
from app.services.convocacoes.analisador import Entrada
from app.services.scraper import EthicalScraper

PLATAFORMA_POR_HOST = (
    ("bsky.app", "bluesky"), ("t.me", "telegram"), ("telegram.me", "telegram"), ("x.com", "x"), ("twitter.com", "x"),
    ("instagram.com", "instagram"), ("facebook.com", "facebook"), ("fb.com", "facebook"), ("tiktok.com", "tiktok"),
    ("youtube.com", "youtube"), ("youtu.be", "youtube"), ("mastodon", "mastodon"),
)


def plataforma_de(url: str) -> str:
    host = urlsplit(url).netloc.lower().removeprefix("www.").removeprefix("m.").removeprefix("mobile.")
    for sufixo, plat in PLATAFORMA_POR_HOST:
        if host == sufixo or host.endswith("." + sufixo) or sufixo in host:
            return plat
    return "web"


@dataclass(slots=True)
class Resolucao:
    entrada: Entrada
    passos: list[str]
    erro: str | None = None


def _meta(html: str, *props: str) -> str | None:
    for prop in props:
        m = re.search(rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if not m:
            m = re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(prop)}["\']', html, re.IGNORECASE)
        if m:
            from html import unescape

            return unescape(m.group(1)).strip()
    return None


async def resolver(scraper: EthicalScraper, url: str, respeitar_robots: bool = True) -> Resolucao:
    url = url.strip()
    plataforma = plataforma_de(url)
    passos: list[str] = []
    entrada = Entrada(post_url=url, plataforma=plataforma)

    # Bluesky via API pública
    partes = bluesky.partes_de_url(url)
    if partes:
        handle, rkey = partes
        did = handle
        if not handle.startswith("did:"):
            r = await scraper.buscar(bluesky.url_resolver_handle(handle), respeitar_robots=respeitar_robots)
            passos.append(f"resolveHandle HTTP {r.status}")
            if r.ok:
                try:
                    did = json.loads(r.html).get("did") or handle
                except ValueError:
                    pass
        r2 = await scraper.buscar(bluesky.url_get_posts(bluesky.at_uri(did, rkey)), respeitar_robots=respeitar_robots)
        passos.append(f"getPosts HTTP {r2.status}")
        cand = bluesky.parse_get_posts(r2.html) if r2.ok else None
        if cand is None:
            return Resolucao(entrada, passos, erro=r2.erro or "post não encontrado na API pública do Bluesky")
        entrada.texto_post = cand.texto_completo
        entrada.autor = cand.autor
        entrada.publicado_em = cand.publicado_em
        if cand.imagens:
            entrada.imagem_url = cand.imagens[0]
            rb = await scraper.buscar_bytes(cand.imagens[0], respeitar_robots=respeitar_robots)
            passos.append(f"imagem HTTP {rb.status}")
            if rb.ok and rb.mime.startswith("image/"):
                entrada.imagem = rb.conteudo
        return Resolucao(entrada, passos)

    # X: oEmbed público (só texto)
    if plataforma == "x":
        r = await scraper.buscar(f"https://publish.twitter.com/oembed?url={quote(url, safe='')}&omit_script=true&lang=pt", respeitar_robots=respeitar_robots)
        passos.append(f"oembed HTTP {r.status}")
        if r.ok:
            try:
                d = json.loads(r.html)
                html = d.get("html", "")
                texto = re.sub(r"<[^>]+>", " ", html)
                from html import unescape

                entrada.texto_post = " ".join(unescape(texto).split())
                entrada.autor = d.get("author_name", "")
            except ValueError:
                pass
        return Resolucao(entrada, passos, erro=None if entrada.texto_post else "X não expõe página pública sem login — cole o texto e solte o print da imagem")

    # Telegram: página de embed do post tem og:image/descrição
    alvo = url
    if plataforma == "telegram" and re.search(r"t\.me/[^/]+/\d+", url) and "embed=" not in url:
        alvo = url + ("&" if "?" in url else "?") + "embed=1"

    rb = await scraper.buscar_bytes(alvo, respeitar_robots=respeitar_robots)
    passos.append(f"GET HTTP {rb.status} {rb.mime}")
    if not rb.ok:
        return Resolucao(entrada, passos, erro=rb.erro or f"HTTP {rb.status}")
    if rb.mime.startswith("image/"):
        entrada.imagem = rb.conteudo
        entrada.imagem_url = url
        entrada.post_url = ""
        return Resolucao(entrada, passos)
    html = rb.conteudo.decode("utf-8", "replace")
    titulo = _meta(html, "og:title", "twitter:title") or ""
    desc = _meta(html, "og:description", "twitter:description", "description") or ""
    entrada.texto_post = "\n".join(p for p in (titulo, desc) if p)
    pub = _meta(html, "article:published_time", "og:updated_time")
    if pub:
        try:
            entrada.publicado_em = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except ValueError:
            pass
    img = _meta(html, "og:image", "og:image:url", "twitter:image", "twitter:image:src")
    if img:
        img = urljoin(url, img)
        entrada.imagem_url = img
        ri = await scraper.buscar_bytes(img, respeitar_robots=respeitar_robots)
        passos.append(f"og:image HTTP {ri.status}")
        if ri.ok and ri.mime.startswith("image/"):
            entrada.imagem = ri.conteudo
    if not entrada.imagem and not entrada.texto_post:
        return Resolucao(entrada, passos, erro="página sem og:image nem texto legível")
    return Resolucao(entrada, passos)
