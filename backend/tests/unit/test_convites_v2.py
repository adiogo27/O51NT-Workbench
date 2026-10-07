from __future__ import annotations

import pytest

from app.services import convites as svc

pytestmark = pytest.mark.unit


def test_extrai_todas_as_formas() -> None:
    txt = (
        "grupo: chat.whatsapp.com/GM4b5kGzIFm36GoyM7AOlM e https://chat.whatsapp.com/invite/GalZzza5qmdGz7dqj3tBv2 "
        "canal https://whatsapp.com/channel/0029VaAbCdEfGhIj12345 telegram t.me/+C7JN-YpjIacxNTQx https://telegram.me/joinchat/AbCdEfGh1234 "
        "publico https://t.me/movimentobrasil e post https://t.me/movimentobrasil/123 servico https://t.me/s/outro https://t.me/share/url?x=1"
    )
    cs = svc.extrair(txt)
    urls = {c.url for c in cs}
    assert "https://chat.whatsapp.com/GM4b5kGzIFm36GoyM7AOlM" in urls and "https://chat.whatsapp.com/GalZzza5qmdGz7dqj3tBv2" in urls
    assert "https://whatsapp.com/channel/0029VaAbCdEfGhIj12345" in urls
    assert "https://t.me/+C7JN-YpjIacxNTQx" in urls and "https://t.me/joinchat/AbCdEfGh1234" in urls
    assert "https://t.me/movimentobrasil" in urls and "https://t.me/outro" not in urls and "https://t.me/s" not in urls and "https://t.me/share" not in urls
    assert {c.plataforma for c in cs} == {"whatsapp", "whatsapp_canal", "telegram", "telegram_publico"}
    assert svc.extrair_convites("nada aqui") == []


def test_compat_scraper_extrair_convites() -> None:
    from app.services.scraper import extrair_convites

    assert extrair_convites("x chat.whatsapp.com/ABCDEFGHIJKLMN y") == [("whatsapp", "https://chat.whatsapp.com/ABCDEFGHIJKLMN")]


def test_queries_searxng_sem_parenteses() -> None:
    qs = svc.montar_queries_searxng('movimento "brasil"')
    assert all("(" not in q and " OR " not in q for q in qs["whatsapp"] + qs["telegram"])
    assert qs["whatsapp"][0] == '"chat.whatsapp.com" movimento brasil' and any(q.startswith("site:x.com") for q in qs["telegram"])
    assert svc.montar_queries_pdf("abc")["whatsapp"].startswith("(site:facebook.com")


WA_OK = '<html><head><meta property="og:title" content="MOVIMENTO BRASIL 🇧🇷"><meta property="og:description" content="WhatsApp Group Invite"><meta property="og:image" content="https://pps.whatsapp.net/v/t61/foto.jpg"></head><body>Join</body></html>'
WA_REVOGADO = '<html><head><meta property="og:title" content="WhatsApp"></head><body><h4>Convite inválido</h4><p>O link de convite foi redefinido.</p></body></html>'
TG_GRUPO = '''<html><body><div class="tgme_page"><div class="tgme_page_photo"><img class="tgme_page_photo_image" src="https://cdn4.telesco.pe/file/x.jpg"></div>
<div class="tgme_page_title"><span dir="auto">Grupo do Telegram MOVIMENTO.BRASIL</span></div><div class="tgme_page_extra">1 234 members, 56 online</div>
<div class="tgme_page_description">Mobilização nacional. Ato dia 11/10.</div><a class="tgme_action_button_new" href="tg://join?invite=x">Join Group</a></div></body></html>'''
TG_CANAL = '<div class="tgme_page_title"><span>Canal X</span></div><div class="tgme_page_extra">12 345 subscribers</div><a class="tgme_action_button_new">View in Telegram</a>'
TG_INVALIDO = '<html><body><div class="tgme_page"><div class="tgme_page_icon"></div><div class="tgme_page_description">Sorry, this link is invalid or has expired.</div></div></body></html>'


def test_parse_landing_whatsapp() -> None:
    v = svc.parse_landing_whatsapp(WA_OK)
    assert v.status == "ativo" and v.nome_grupo == "MOVIMENTO BRASIL 🇧🇷" and v.membros is None and v.foto_url.endswith("foto.jpg")
    assert svc.parse_landing_whatsapp(WA_REVOGADO).status == "revogado"
    assert svc.parse_landing_whatsapp("<html></html>", 404).status == "revogado"
    assert svc.parse_landing("https://chat.whatsapp.com/abc", "", 200).status == "desconhecido"


def test_parse_landing_telegram() -> None:
    v = svc.parse_landing_telegram(TG_GRUPO)
    assert v.status == "ativo" and v.membros == 1234 and v.tipo == "grupo" and "11/10" in (v.descricao or "") and v.foto_url.endswith("x.jpg")
    c = svc.parse_landing_telegram(TG_CANAL)
    assert c.status == "ativo" and c.membros == 12345 and c.tipo == "canal"
    assert svc.parse_landing_telegram(TG_INVALIDO).status == "revogado"
    assert svc.score_relevancia("MOVIMENTO BRASIL", "Ato dia 11/10 em BH. Vem pra rua!") >= 40
