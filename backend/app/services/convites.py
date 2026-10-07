"""Convites de grupos (WhatsApp/Telegram): extração v2, dorks amigáveis ao SearXNG e verificação da página pública.

Verificar = um GET da landing pública do convite (o mesmo que qualquer preview de link faz). Nunca entra no grupo,
nunca lista membros (só o agregado que a própria página exibe). Passa pelo EthicalScraper (backoff → robots → rate limit).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from html import unescape
from typing import Literal
from urllib.parse import unquote

from app.models._base import agora

Plataforma = Literal["whatsapp", "whatsapp_canal", "telegram", "telegram_publico"]

_WHATSAPP_RE = re.compile(r"https?://chat\.whatsapp\.com/(?:invite/)?([A-Za-z0-9]{10,40})")
_WA_CANAL_RE = re.compile(r"https?://(?:www\.)?whatsapp\.com/channel/([A-Za-z0-9]{10,40})")
_TG_PRIV_RE = re.compile(r"https?://(?:t|telegram)\.me/(?:joinchat/([A-Za-z0-9_-]{8,64})|\+([A-Za-z0-9_-]{8,64}))")
# público: t.me/<user>; exclui rotas de serviço e caminhos com post id (t.me/canal/123 → canal público "canal")
_TG_PUB_RE = re.compile(
    r"https?://(?:t|telegram)\.me/(?!(?:s|joinchat|share|proxy|socks|addstickers|addemoji|addtheme|iv|setlanguage|login|contact|confphone|bg|boost|c|m|a)(?:/|$|\?))"
    r"([A-Za-z][A-Za-z0-9_]{3,31})(?:/\d+)?/?(?![\w/@+-])"
)
_SEM_ESQUEMA_RE = re.compile(r"(?<![/\w.@])((?:chat\.whatsapp\.com|t\.me|telegram\.me|whatsapp\.com/channel)/)")
_SERVICO_TG = frozenset({"s", "joinchat", "share", "proxy", "socks", "addstickers", "addemoji", "addtheme", "iv", "setlanguage", "login", "contact", "confphone", "bg", "boost", "c", "m", "a", "privacy", "tos", "faq", "apps"})


@dataclass(slots=True)
class Convite:
    plataforma: str
    url: str  # canônica
    codigo: str


def _normalizar(texto: str) -> str:
    # buscadores encapsulam links (DuckDuckGo uddg=...): desfaz percent-encoding e entidades; acrescenta https:// a links nus
    return _SEM_ESQUEMA_RE.sub(r"https://\1", unquote(unescape(texto or "")))


def extrair(texto: str) -> list[Convite]:
    """Convites únicos, na ordem em que aparecem (privados antes de públicos quando empatam na posição)."""
    t = _normalizar(texto)
    achados: list[tuple[int, int, Convite]] = []
    for m in _WHATSAPP_RE.finditer(t):
        achados.append((m.start(), 0, Convite("whatsapp", f"https://chat.whatsapp.com/{m.group(1)}", m.group(1))))
    for m in _WA_CANAL_RE.finditer(t):
        achados.append((m.start(), 0, Convite("whatsapp_canal", f"https://whatsapp.com/channel/{m.group(1)}", m.group(1))))
    for m in _TG_PRIV_RE.finditer(t):
        cod = m.group(1) or m.group(2)
        url = f"https://t.me/joinchat/{cod}" if m.group(1) else f"https://t.me/+{cod}"
        achados.append((m.start(), 0, Convite("telegram", url, cod)))
    for m in _TG_PUB_RE.finditer(t):
        user = m.group(1)
        if user.lower() in _SERVICO_TG:
            continue
        achados.append((m.start(), 1, Convite("telegram_publico", f"https://t.me/{user}", user)))
    vistos: dict[str, Convite] = {}
    for _, _, c in sorted(achados, key=lambda x: (x[0], x[1])):
        vistos.setdefault(c.url.lower(), c)
    return list(vistos.values())


def extrair_convites(texto: str) -> list[tuple[str, str]]:
    """Compatível com a API antiga de `scraper.extrair_convites`: [(plataforma, url)]."""
    return [(c.plataforma, c.url) for c in extrair(texto)]


# ------------------------------------------------------------------ dorks
REDES_PDF = "(site:facebook.com OR site:instagram.com OR site:x.com OR site:tiktok.com)"
PADROES_PDF = {
    "whatsapp": REDES_PDF + ' (chat.whatsapp.com "{termo}")',
    "telegram": REDES_PDF + ' (t.me/joinchat "{termo}")',
}
REDES_SEARXNG = ("x.com", "instagram.com", "facebook.com", "tiktok.com")


def limpar_termo(termo: str) -> str:
    return " ".join(termo.replace('"', " ").split())


def montar_queries_pdf(termo: str) -> dict[str, str]:
    t = limpar_termo(termo)
    return {plat: padrao.format(termo=t) for plat, padrao in PADROES_PDF.items()}


def montar_queries_searxng(termo: str) -> dict[str, list[str]]:
    """Variantes sem parênteses/OR (Bing/DDG honram `site:` simples e aspas). Uma consulta por item."""
    t = limpar_termo(termo)
    wa = [f'"chat.whatsapp.com" {t}'] + [f'site:{r} "chat.whatsapp.com" {t}' for r in REDES_SEARXNG]
    tg = [f'"t.me/+" {t}', f'"t.me/joinchat" {t}'] + [f'site:{r} "t.me" {t}' for r in REDES_SEARXNG]
    return {"whatsapp": wa, "telegram": tg}


# ------------------------------------------------------------------ verificação (parsers puros)
@dataclass(slots=True)
class VerificacaoConvite:
    status: Literal["ativo", "revogado", "desconhecido"] = "desconhecido"
    nome_grupo: str | None = None
    membros: int | None = None
    descricao: str | None = None
    foto_url: str | None = None
    http_status: int = 0
    erro: str | None = None
    robots_permite: bool = True
    verificado_em: datetime = field(default_factory=agora)
    sha256_pagina: str = ""
    tipo: str = ""  # grupo | canal | usuario

    def como_dict(self) -> dict:
        return {
            "status": self.status,
            "nome_grupo": self.nome_grupo,
            "membros": self.membros,
            "descricao": self.descricao,
            "foto_url": self.foto_url,
            "http_status": self.http_status,
            "erro": self.erro,
            "robots_permite": self.robots_permite,
            "verificado_em": self.verificado_em.isoformat(),
            "sha256_pagina": self.sha256_pagina,
            "tipo": self.tipo,
        }


_INVALIDOS_WA = ("convite inválido", "convite invalido", "invite link is invalid", "link de convite foi redefinido", "invite link reset",
                 "grupo não encontrado", "o link de convite não é válido", "link has been reset", "invite link was reset")
_INVALIDOS_TG = ("link is invalid", "link has expired", "isn't accessible", "is not accessible", "has been deleted", "doesn't exist",
                 "if you have telegram, you can contact")  # última: página genérica de usuário inexistente mostra só o CTA
_NUM_RE = re.compile(r"([\d][\d\s .,]*)\s*(members|subscribers|membros|inscritos|assinantes|participantes)", re.IGNORECASE)


def _meta(soup, prop: str) -> str | None:  # noqa: ANN001
    el = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    v = (el.get("content") if el else None) or None
    return " ".join(str(v).split()) if v else None


def _int_de(texto: str) -> int | None:
    m = _NUM_RE.search(texto or "")
    if not m:
        return None
    digitos = re.sub(r"\D", "", m.group(1))
    return int(digitos) if digitos else None


def parse_landing_whatsapp(html: str, http_status: int = 200) -> VerificacaoConvite:
    from bs4 import BeautifulSoup

    v = VerificacaoConvite(http_status=http_status, tipo="grupo")
    soup = BeautifulSoup(html or "", "lxml")
    texto = soup.get_text(" ").lower()
    titulo = _meta(soup, "og:title")
    desc = _meta(soup, "og:description")
    foto = _meta(soup, "og:image")
    if any(p in texto for p in _INVALIDOS_WA) or http_status == 404:
        v.status = "revogado"
        v.nome_grupo = titulo if titulo and titulo.lower() not in ("whatsapp", "whatsapp group invite", "whatsapp.com") else None
        return v
    if titulo and titulo.lower() not in ("whatsapp", "whatsapp.com"):
        v.status = "ativo"
        v.nome_grupo = titulo
        v.descricao = desc
        v.foto_url = foto
        if desc and "channel" in desc.lower():
            v.tipo = "canal"
        return v
    v.status = "desconhecido"
    v.erro = "página sem og:title (bloqueio/JS?)"
    return v


def parse_landing_telegram(html: str, http_status: int = 200) -> VerificacaoConvite:
    from bs4 import BeautifulSoup

    v = VerificacaoConvite(http_status=http_status)
    soup = BeautifulSoup(html or "", "lxml")
    texto = soup.get_text(" ").lower()
    titulo_el = soup.select_one(".tgme_page_title")
    extra_el = soup.select_one(".tgme_page_extra")
    desc_el = soup.select_one(".tgme_page_description")
    foto_el = soup.select_one(".tgme_page_photo_image img, img.tgme_page_photo_image")
    botao = soup.select_one(".tgme_action_button_new, a.tgme_action_button_new, .tgme_page_action a")
    titulo = " ".join(titulo_el.get_text(" ").split()) if titulo_el else None
    extra = " ".join(extra_el.get_text(" ").split()) if extra_el else ""
    if http_status == 404 or titulo is None or any(p in texto for p in _INVALIDOS_TG[:6]):
        v.status = "revogado" if (titulo is None or any(p in texto for p in _INVALIDOS_TG[:6])) else "desconhecido"
        if v.status == "revogado" and http_status not in (200, 404) and titulo is None:
            v.status = "desconhecido"
            v.erro = f"HTTP {http_status}"
        return v
    v.status = "ativo"
    v.nome_grupo = titulo
    v.membros = _int_de(extra)
    v.descricao = " ".join(desc_el.get_text(" ").split()) if desc_el else None
    v.foto_url = (foto_el.get("src") if foto_el else None) or _meta(soup, "og:image")
    rotulo_botao = (botao.get_text(" ").strip().lower() if botao else "")
    if "members" in extra.lower() or "join group" in rotulo_botao:
        v.tipo = "grupo"
    elif "subscribers" in extra.lower() or "channel" in rotulo_botao:
        v.tipo = "canal"
    elif extra.startswith("@"):
        v.tipo = "usuario"
    return v


def parse_landing(url: str, html: str, http_status: int = 200) -> VerificacaoConvite:
    if "whatsapp.com" in url:
        return parse_landing_whatsapp(html, http_status)
    return parse_landing_telegram(html, http_status)


async def verificar(scraper, inv, respeitar_robots: bool = True) -> VerificacaoConvite:  # noqa: ANN001
    """GET da landing pública do convite via EthicalScraper. `inv` precisa de `.url`."""
    url = inv.url if hasattr(inv, "url") else str(inv)
    robots_ok = await scraper.robots.permitido(url)
    res = await scraper.buscar(url, respeitar_robots=respeitar_robots)
    if res.erro and not res.html:
        v = VerificacaoConvite(http_status=res.status, erro=res.erro, robots_permite=robots_ok)
        return v
    v = parse_landing(url, res.html, res.status)
    v.robots_permite = robots_ok
    v.sha256_pagina = res.sha256
    if res.erro and v.status == "desconhecido":
        v.erro = res.erro
    return v


def score_relevancia(nome: str | None, descricao: str | None, contexto: str = "") -> int:
    from app.services.convocacoes import lexico_mobilizacao as lexico

    return lexico.avaliar(" ".join(p for p in (nome or "", descricao or "", contexto) if p)).score
