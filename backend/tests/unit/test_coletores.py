from __future__ import annotations

import json

import pytest

from app.services.convocacoes import bluesky, telegram

pytestmark = pytest.mark.unit

BSKY = {
    "cursor": "abc",
    "posts": [
        {
            "uri": "at://did:plc:xyz/app.bsky.feed.post/3kabc",
            "author": {"did": "did:plc:xyz", "handle": "coletivo.bsky.social"},
            "record": {"text": "Revolta nas ruas! Dia 11 em BH", "createdAt": "2026-10-05T12:00:00.000Z", "langs": ["pt"]},
            "embed": {"$type": "app.bsky.embed.images#view", "images": [{"fullsize": "https://cdn.bsky.app/img/full/1.jpg", "thumb": "https://cdn.bsky.app/img/thumb/1.jpg", "alt": "Cartaz: ATO NÃO PACÍFICO 11/10"}]},
            "likeCount": 3,
        },
        {
            "uri": "at://did:plc:abc/app.bsky.feed.post/3kdef",
            "author": {"did": "did:plc:abc", "handle": "outro.bsky.social"},
            "record": {"text": "citando", "createdAt": "2026-10-05T13:00:00Z"},
            "embed": {"$type": "app.bsky.embed.recordWithMedia#view", "media": {"$type": "app.bsky.embed.images#view", "images": [{"fullsize": "https://cdn.bsky.app/img/full/2.jpg", "thumb": "https://cdn.bsky.app/img/thumb/2.jpg", "alt": ""}]}, "record": {}},
        },
        {"uri": "at://did:plc:q/app.bsky.feed.post/3kq", "author": {"handle": "semimg.bsky.social"}, "record": {"text": "só texto", "createdAt": "x"}},
    ],
}


def test_bluesky_parse_e_urls() -> None:
    cands, cursor = bluesky.parse_busca(json.dumps(BSKY))
    assert cursor == "abc" and len(cands) == 3
    c = cands[0]
    assert c.post_url == "https://bsky.app/profile/coletivo.bsky.social/post/3kabc" and c.imagens == ["https://cdn.bsky.app/img/full/1.jpg"]
    assert "ATO NÃO PACÍFICO" in c.texto_completo and c.publicado_em.year == 2026 and c.autor == "@coletivo.bsky.social"
    assert cands[1].imagens == ["https://cdn.bsky.app/img/full/2.jpg"] and cands[2].imagens == [] and cands[2].publicado_em is None
    u = bluesky.url_busca("ato não pacífico", limite=25)
    assert u.startswith(bluesky.URL_BUSCA) and "q=ato+n%C3%A3o+pac%C3%ADfico" in u and "limit=25" in u and "sort=latest" in u and "lang=pt" in u
    assert bluesky.partes_de_url("https://bsky.app/profile/coletivo.bsky.social/post/3kabc") == ("coletivo.bsky.social", "3kabc")
    assert bluesky.at_uri("did:plc:xyz", "3kabc") == "at://did:plc:xyz/app.bsky.feed.post/3kabc"
    assert bluesky.parse_get_posts(json.dumps({"posts": BSKY["posts"][:1]})).post_url.endswith("/post/3kabc")


TME = '''<html><body><div class="tgme_channel_info"><div class="tgme_channel_info_header_title"><span>MOVIMENTO.BRASIL</span></div>
<div class="tgme_channel_info_counters"><div class="tgme_channel_info_counter"><span class="counter_value">4 567</span> <span class="counter_type">subscribers</span></div>
<div class="tgme_channel_info_counter"><span class="counter_value">120</span> <span class="counter_type">photos</span></div></div>
<div class="tgme_channel_info_description">Canal oficial</div></div>
<section class="tgme_channel_history"><a class="tme_messages_more" data-before="100" href="/s/movimentobrasil?before=100">more</a>
<div class="tgme_widget_message" data-post="movimentobrasil/101"><div class="tgme_widget_message_bubble">
<a class="tgme_widget_message_photo_wrap" href="https://t.me/movimentobrasil/101" style="width:800px;background-image:url('https://cdn4.telesco.pe/file/a.jpg')"></a>
<div class="tgme_widget_message_text">Dia 11/10 ato não pacífico em BH. Grupo: <a href="https://t.me/+C7JN-YpjIacxNTQx">entre</a></div>
<span class="tgme_widget_message_views">1.2K</span><a class="tgme_widget_message_date" href="#"><time datetime="2026-10-05T10:00:00+00:00"></time></a></div></div>
<div class="tgme_widget_message" data-post="movimentobrasil/102"><div class="tgme_widget_message_grouped_wrap"><a style="background-image:url('https://cdn4.telesco.pe/file/b.jpg')"></a><a style="background-image:url('https://cdn4.telesco.pe/file/c.jpg')"></a></div>
<div class="tgme_widget_message_forwarded_from_name">Outro canal</div><time datetime="2026-10-05T11:00:00+00:00"></time></div>
<div class="tgme_widget_message" data-post="movimentobrasil/103"><div class="tgme_widget_message_text">só texto</div></div>
</section></body></html>'''


def test_telegram_parse_canal() -> None:
    c = telegram.parse_canal(TME, "@movimentobrasil")
    assert c.canal == "movimentobrasil" and c.nome == "MOVIMENTO.BRASIL" and c.assinantes == 4567 and c.anterior == "100"
    assert len(c.posts) == 3
    p = c.posts[0]
    assert p.post_url == "https://t.me/movimentobrasil/101" and p.imagens == ["https://cdn4.telesco.pe/file/a.jpg"] and "t.me/+C7JN-YpjIacxNTQx" in p.texto
    assert p.publicado_em.day == 5 and p.extra["views"] == "1.2K" and p.autor == "@movimentobrasil"
    assert c.posts[1].imagens == ["https://cdn4.telesco.pe/file/b.jpg", "https://cdn4.telesco.pe/file/c.jpg"] and c.posts[1].extra["encaminhado_de"] == "Outro canal"
    assert c.posts[2].imagens == []
    assert telegram.url_canal("https://t.me/s/movimentobrasil/") == "https://t.me/s/movimentobrasil"
    assert telegram.url_canal("@canal", "100") == "https://t.me/s/canal?before=100"
    assert telegram.normalizar_canal("https://t.me/canal?x=1") == "canal"
