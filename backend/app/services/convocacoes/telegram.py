"""Telegram público sem login: pré-visualização de canal `t.me/s/<canal>` (posts, fotos, datas, links). Parser puro."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.services.convocacoes.bluesky import PostCandidato

_URL_BG_RE = re.compile(r"url\(['\"]?([^'\")]+)['\"]?\)")


@dataclass(slots=True)
class CanalTelegram:
    canal: str
    nome: str = ""
    assinantes: int | None = None
    descricao: str = ""
    posts: list[PostCandidato] = field(default_factory=list)
    anterior: str | None = None  # data-before para paginação


def normalizar_canal(valor: str) -> str:
    v = valor.strip()
    v = re.sub(r"^https?://(?:t|telegram)\.me/(?:s/)?", "", v, flags=re.IGNORECASE)
    return v.strip("/@ ").split("/")[0].split("?")[0]


def url_canal(canal: str, antes_de: str | None = None) -> str:
    base = f"https://t.me/s/{normalizar_canal(canal)}"
    return f"{base}?before={antes_de}" if antes_de else base


def _int(texto: str) -> int | None:
    d = re.sub(r"\D", "", texto or "")
    return int(d) if d else None


def _data(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_canal(html: str, canal: str = "") -> CanalTelegram:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "lxml")
    out = CanalTelegram(canal=normalizar_canal(canal))
    t = soup.select_one(".tgme_channel_info_header_title")
    out.nome = " ".join(t.get_text(" ").split()) if t else ""
    d = soup.select_one(".tgme_channel_info_description")
    out.descricao = " ".join(d.get_text(" ").split()) if d else ""
    for c in soup.select(".tgme_channel_info_counters .tgme_channel_info_counter"):
        tipo = (c.select_one(".counter_type") or c).get_text(" ").lower()
        if "subscriber" in tipo or "member" in tipo:
            val = c.select_one(".counter_value")
            out.assinantes = _int(val.get_text() if val else "")
    mais = soup.select_one("a.tme_messages_more[data-before]")
    out.anterior = mais.get("data-before") if mais else None
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        post_id = msg.get("data-post", "")
        if not post_id:
            continue
        canal_id = post_id.split("/")[0]
        texto_el = msg.select_one(".tgme_widget_message_text")
        texto = " ".join(texto_el.get_text(" ").split()) if texto_el else ""
        imagens: list[str] = []
        for a in msg.select("a.tgme_widget_message_photo_wrap, .tgme_widget_message_grouped_wrap a[style]"):
            m = _URL_BG_RE.search(a.get("style", ""))
            if m and m.group(1) not in imagens:
                imagens.append(m.group(1))
        for v in msg.select(".tgme_widget_message_video_thumb[style]"):
            m = _URL_BG_RE.search(v.get("style", ""))
            if m and m.group(1) not in imagens:
                imagens.append(m.group(1))
        time_el = msg.select_one(".tgme_widget_message_date time[datetime], time[datetime]")
        views_el = msg.select_one(".tgme_widget_message_views")
        fwd = msg.select_one(".tgme_widget_message_forwarded_from_name")
        links = [a.get("href", "") for a in msg.select(".tgme_widget_message_text a[href], a.tgme_widget_message_link_preview[href]") if a.get("href")]
        autor_el = msg.select_one(".tgme_widget_message_owner_name")
        out.posts.append(
            PostCandidato(
                post_url=f"https://t.me/{post_id}",
                plataforma="telegram",
                autor=f"@{canal_id}" if canal_id else (" ".join(autor_el.get_text(" ").split()) if autor_el else ""),
                texto=texto + (("\n" + " ".join(links)) if links else ""),
                publicado_em=_data(time_el.get("datetime") if time_el else None),
                imagens=imagens,
                miniaturas=imagens,
                extra={"views": views_el.get_text(" ").strip() if views_el else None, "encaminhado_de": " ".join(fwd.get_text(" ").split()) if fwd else None, "links": links},
            )
        )
    return out
