"""Bluesky: API pública (sem autenticação) — busca de posts e resolução de URL de post. Funções puras + montagem de URLs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote, urlencode

API = "https://public.api.bsky.app/xrpc"
URL_BUSCA = f"{API}/app.bsky.feed.searchPosts"
_POST_URL_RE = re.compile(r"https?://bsky\.app/profile/([^/]+)/post/([A-Za-z0-9]+)")


@dataclass(slots=True)
class PostCandidato:
    post_url: str
    plataforma: str
    autor: str = ""
    texto: str = ""
    publicado_em: datetime | None = None
    imagens: list[str] = field(default_factory=list)  # URLs (fullsize) na ordem
    miniaturas: list[str] = field(default_factory=list)
    alts: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def texto_completo(self) -> str:
        return "\n".join(p for p in (self.texto, *self.alts) if p)


def url_busca(termo: str, limite: int = 50, ordem: Literal["latest", "top"] = "latest", lang: str | None = "pt", desde: datetime | None = None, cursor: str | None = None) -> str:
    params: dict[str, str] = {"q": termo, "limit": str(max(1, min(100, limite))), "sort": ordem}
    if lang:
        params["lang"] = lang
    if desde:
        params["since"] = desde.strftime("%Y-%m-%dT%H:%M:%SZ")
    if cursor:
        params["cursor"] = cursor
    return f"{URL_BUSCA}?{urlencode(params)}"


def url_resolver_handle(handle: str) -> str:
    return f"{API}/com.atproto.identity.resolveHandle?handle={quote(handle)}"


def url_get_posts(uri_at: str) -> str:
    return f"{API}/app.bsky.feed.getPosts?uris={quote(uri_at, safe='')}"


def partes_de_url(url_post: str) -> tuple[str, str] | None:
    m = _POST_URL_RE.match(url_post.strip())
    return (m.group(1), m.group(2)) if m else None


def at_uri(did: str, rkey: str) -> str:
    return f"at://{did}/app.bsky.feed.post/{rkey}"


def url_web(uri_at: str, handle: str) -> str:
    rkey = uri_at.rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def _data(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def _imagens_de_embed(embed: dict | None) -> tuple[list[str], list[str], list[str]]:
    if not embed:
        return [], [], []
    tipo = embed.get("$type", "")
    if tipo.startswith("app.bsky.embed.images"):
        imgs = embed.get("images") or []
        return [i.get("fullsize", "") for i in imgs if i.get("fullsize")], [i.get("thumb", "") for i in imgs], [i.get("alt", "") for i in imgs if i.get("alt")]
    if tipo.startswith("app.bsky.embed.recordWithMedia"):
        return _imagens_de_embed(embed.get("media"))
    if tipo.startswith("app.bsky.embed.external"):
        th = (embed.get("external") or {}).get("thumb")
        return ([th], [th], []) if th else ([], [], [])
    if tipo.startswith("app.bsky.embed.video"):
        th = embed.get("thumbnail")
        return ([th], [th], [embed.get("alt", "")] if embed.get("alt") else []) if th else ([], [], [])
    return [], [], []


def post_para_candidato(post: dict) -> PostCandidato | None:
    uri = post.get("uri") or ""
    autor = post.get("author") or {}
    handle = autor.get("handle") or autor.get("did") or ""
    if not uri or not handle:
        return None
    rec = post.get("record") or {}
    imgs, thumbs, alts = _imagens_de_embed(post.get("embed"))
    return PostCandidato(
        post_url=url_web(uri, handle),
        plataforma="bluesky",
        autor=f"@{handle}",
        texto=rec.get("text", "") or "",
        publicado_em=_data(rec.get("createdAt")),
        imagens=imgs,
        miniaturas=thumbs,
        alts=alts,
        extra={"uri": uri, "likes": post.get("likeCount", 0), "reposts": post.get("repostCount", 0), "langs": rec.get("langs", [])},
    )


def parse_busca(json_texto: str | bytes) -> tuple[list[PostCandidato], str | None]:
    """(candidatos, cursor). Posts sem imagem também voltam (texto pode ser convocação) — quem coleta decide."""
    dados = json.loads(json_texto)
    out: list[PostCandidato] = []
    for p in dados.get("posts", []):
        c = post_para_candidato(p)
        if c is not None:
            out.append(c)
    return out, dados.get("cursor")


def parse_get_posts(json_texto: str | bytes) -> PostCandidato | None:
    dados = json.loads(json_texto)
    posts = dados.get("posts") or []
    return post_para_candidato(posts[0]) if posts else None
