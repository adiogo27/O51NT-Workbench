"""Radar: coleta contínua de feeds públicos e casamento com as queries de TODOS os monitores ativos.

Por que feeds: buscadores bloqueiam coleta automatizada (CAPTCHA/robots.txt). RSS/Atom existem
exatamente para leitura por máquina — imprensa, Mastodon (hashtags) e o feed pessoal do Google
Alertas (a busca do Google entregue pelo próprio Google para leitores de feed).

O matcher interpreta a MESMA sintaxe do Query Builder (tokenizador de operators.py):
- termos e "frases" (com curinga *), AND implícito, OR, parênteses, -negação, #hashtag, @menção;
- site:/-site: (modo "estrito": casa pelo domínio do item; modo "termos": ignorado);
- after:/before: e since:/until: (data de publicação); intitle:/inurl:/intext:/filetype:;
- demais operadores (is:, has:, lang:, from:, …) são filtros de motor e não restringem.
Comparação sem acentos e sem distinção de caixa.
"""

from __future__ import annotations

import asyncio
import hashlib
import html as html_mod
import json
import logging
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models._base import agora
from app.models.monitor import Monitor
from app.models.radar import Fonte, FonteItem, MonitorHit
from app.services import alerts
from app.services.operators import OPERADORES_CHAVE, OPERADORES_X_CHAVE, TipoToken, Token, tokenizar
from app.services.scraper import EthicalScraper

logger = logging.getLogger("o51nt.radar")

RESUMO_MAX = 1200
ULTIMO_CICLO: dict[str, Any] | None = None  # resumo do último ciclo (em memória; as fontes guardam o persistido)


# ------------------------------------------------------------------ feeds
@dataclass(slots=True)
class ItemFeed:
    url: str
    titulo: str = ""
    resumo: str = ""
    publicado_em: datetime | None = None
    midias: list[str] = field(default_factory=list)  # imagens (enclosure/media:content) — módulo Convocações


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _texto(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return "".join(el.itertext()).strip() if len(el) else (el.text or "").strip()


def _primeiro(campos: dict[str, ET.Element], *nomes: str) -> ET.Element | None:
    """Primeiro campo presente. (Não usar `a or b`: Element sem filhos é falso no ElementTree.)"""
    for n in nomes:
        el = campos.get(n)
        if el is not None:
            return el
    return None


def limpar_html(texto: str) -> str:
    """Remove tags/entidades de descrições de feed e colapsa espaços."""
    if not texto:
        return ""
    if "<" in texto and ">" in texto:
        from bs4 import BeautifulSoup

        texto = BeautifulSoup(texto, "lxml").get_text(" ")
    return " ".join(html_mod.unescape(texto).split())


def parse_data(valor: str | None) -> datetime | None:
    v = (valor or "").strip()
    if not v:
        return None
    dt: datetime | None = None
    try:
        dt = parsedate_to_datetime(v)  # RFC 822 (RSS)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))  # ISO 8601 (Atom)
        except ValueError:
            return None
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_feed(texto: str) -> list[ItemFeed]:
    """RSS 2.0, RSS 1.0 (RDF) e Atom. Ignora itens sem link; deduplica por URL dentro do feed."""
    try:
        raiz = ET.fromstring(texto.strip().encode("utf-8", "replace"))
    except ET.ParseError as exc:
        raise ValueError(f"feed inválido (XML): {exc}") from exc
    tipo = _local(raiz.tag)
    if tipo not in ("rss", "rdf", "feed"):
        raise ValueError(f"feed inválido: raiz <{tipo}> não é rss/rdf/feed")
    itens: list[ItemFeed] = []
    vistos: set[str] = set()
    for el in raiz.iter():
        nome = _local(el.tag)
        if nome not in ("item", "entry"):
            continue
        campos: dict[str, ET.Element] = {}
        link = ""
        midias: list[str] = []
        for filho in el:
            n = _local(filho.tag)
            if n in ("enclosure", "content", "thumbnail") and filho.get("url"):
                tipo_m = (filho.get("type") or "").lower()
                medium = (filho.get("medium") or "").lower()
                if n == "thumbnail" or tipo_m.startswith("image/") or medium == "image" or (n == "enclosure" and not tipo_m and re.search(r"\.(?:jpe?g|png|webp|gif)(?:\?|$)", filho.get("url", ""), re.I)):
                    u = filho.get("url", "").strip()
                    if u.startswith(("http://", "https://")) and u not in midias:
                        midias.append(u)
                if n == "content" and "}" in filho.tag:  # media:content não é o content:encoded
                    continue
            if n == "link":
                href = (filho.get("href") or "").strip()
                rel = (filho.get("rel") or "alternate").lower()
                if href and (not link or rel == "alternate"):
                    link = href
                elif not href and not link:
                    link = _texto(filho)
            else:
                campos.setdefault(n, filho)
        if not link:
            guid = campos.get("guid")
            if guid is not None and (guid.text or "").strip().startswith(("http://", "https://")):
                link = (guid.text or "").strip()
        link = link.strip()
        if not link.startswith(("http://", "https://")) or link in vistos:
            continue
        vistos.add(link)
        titulo = limpar_html(_texto(campos.get("title")))
        resumo = limpar_html(_texto(_primeiro(campos, "encoded", "description", "summary", "content")))
        if not titulo:
            titulo = resumo[:120]  # Mastodon: itens sem <title>
        publicado = parse_data(_texto(_primeiro(campos, "pubdate", "published", "updated", "date")))
        itens.append(ItemFeed(url=link, titulo=titulo[:300], resumo=resumo[:RESUMO_MAX], publicado_em=publicado, midias=midias[:6]))
    return itens


# ------------------------------------------------------------------ páginas HTML (fontes sem RSS)
_EXT_NAO_ARTIGO = re.compile(r"\.(?:jpe?g|png|gif|webp|svg|ico|pdf|mp4|mp3|zip|css|js|xml|json)(?:\?|$)", re.I)


def descobrir_feed(html_texto: str, base_url: str) -> str | None:
    """URL do RSS/Atom anunciado em <link rel="alternate" type="application/rss+xml">, se houver."""
    if not html_texto or "<link" not in html_texto.lower():
        return None
    from bs4 import BeautifulSoup

    sopa = BeautifulSoup(html_texto, "lxml")
    for link in sopa.find_all("link"):
        rel = " ".join(link.get("rel") or []).lower()
        tipo = (link.get("type") or "").lower()
        href = (link.get("href") or "").strip()
        if "alternate" in rel and href and ("rss" in tipo or "atom" in tipo):
            u = urljoin(base_url, href)
            if u.startswith(("http://", "https://")):
                return u
    return None


def parse_pagina(html_texto: str, base_url: str, max_itens: int = 100) -> list[ItemFeed]:
    """Links de matérias numa página de notícias sem RSS: mesmo host, fora de nav/rodapé, texto da âncora ≥ 25 caracteres."""
    if not html_texto:
        return []
    from bs4 import BeautifulSoup

    sopa = BeautifulSoup(html_texto, "lxml")
    for tag in sopa.find_all(["nav", "header", "footer", "aside", "script", "style", "noscript", "form", "svg"]):
        tag.decompose()
    for tag in sopa.select('[role="navigation"], [role="banner"], [role="contentinfo"], [aria-hidden="true"]'):
        tag.decompose()
    base = urlsplit(base_url)
    host = base.netloc.lower().removeprefix("www.")
    base_limpa = urlunsplit((base.scheme, base.netloc, base.path.rstrip("/"), "", ""))
    itens: list[ItemFeed] = []
    vistos: set[str] = set()
    for a in sopa.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:", "whatsapp:")):
            continue
        url = urljoin(base_url, href)
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or p.netloc.lower().removeprefix("www.") != host:
            continue
        url = urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))
        if url.rstrip("/") == base_limpa or len(p.path.strip("/")) < 2 or _EXT_NAO_ARTIGO.search(p.path):
            continue
        texto = " ".join(a.get_text(" ").split()) or " ".join((a.get("title") or "").split())
        chave = urlunsplit((p.scheme, host, p.path, p.query, ""))  # com e sem www. é o mesmo link
        if len(texto) < 25 or chave in vistos:
            continue
        vistos.add(chave)
        itens.append(ItemFeed(url=url, titulo=texto[:300]))
        if len(itens) >= max_itens:
            break
    return itens


def hash_conteudo(html_texto: str) -> str:
    """SHA-256 do texto visível (sem tags/espacos) — detecta mudança da página entre verificações."""
    return hashlib.sha256(limpar_html(html_texto or "").encode("utf-8", "replace")).hexdigest()


def fonte_devida(fonte: Fonte, agora_: datetime) -> bool:
    """Fonte com intervalo próprio só é coletada quando o intervalo venceu; sem intervalo, segue o ciclo global."""
    intervalo = getattr(fonte, "intervalo_min", None)
    if not intervalo or fonte.ultima_coleta is None:
        return True
    ultima = fonte.ultima_coleta if fonte.ultima_coleta.tzinfo else fonte.ultima_coleta.replace(tzinfo=UTC)
    return agora_ - ultima >= timedelta(minutes=intervalo)


# ------------------------------------------------------------------ matcher
def normalizar(texto: str) -> str:
    """NFKD sem marcas combinantes + casefold + espaços colapsados (mesma regra das hashtags)."""
    decomposto = unicodedata.normalize("NFKD", texto or "")
    return " ".join("".join(c for c in decomposto if not unicodedata.combining(c)).casefold().split())


def _regex_termo(valor: str, tipo: TipoToken) -> re.Pattern[str]:
    v = normalizar(valor)
    if tipo is TipoToken.FRASE:
        v = v.strip('"').strip()
        partes = [re.escape(p) for p in v.split(" ") if p]
        corpo = r"\s+".join(r".+?" if p == r"\*" else p for p in partes)
        return re.compile(rf"(?<![\w#@]){corpo}(?!\w)")
    if tipo is TipoToken.HASHTAG:
        return re.compile(rf"(?<!\w)#?{re.escape(v.lstrip('#'))}(?!\w)")
    if tipo is TipoToken.MENCAO:
        return re.compile(rf"(?<!\w)@?{re.escape(v.lstrip('@'))}(?!\w)")
    # termo solto com curinga: "manifesta*" casa manifestação/manifestantes/manifestam (prefixo/infixo, só dentro da palavra)
    corpo = re.escape(v).replace(r"\*", r"\w*")
    return re.compile(rf"(?<![\w#@]){corpo}(?!\w)")


# AST: ("and", [nós]) | ("or", [nós]) | ("term", rotulo, regex, negado) | ("op", chave, valor, negado) | ("true",)
Node = tuple


def _parse_atom(tokens: list[Token], i: int) -> tuple[Node | None, int]:
    t = tokens[i]
    if t.tipo is TipoToken.ABRE:
        no, j = _parse_expr(tokens, i + 1)
        if j < len(tokens) and tokens[j].tipo is TipoToken.FECHA:
            j += 1
        return no, j
    if t.tipo in (TipoToken.TERMO, TipoToken.FRASE, TipoToken.HASHTAG, TipoToken.MENCAO):
        if t.tipo is TipoToken.TERMO and t.valor.lower() in ("and", "or"):
            return ("true",), i + 1
        return ("term", t.valor, _regex_termo(t.valor, t.tipo), t.negado), i + 1
    if t.tipo is TipoToken.OPERADOR:
        return ("op", t.chave or "", t.valor.strip('"'), t.negado), i + 1
    return ("true",), i + 1  # CURINGA solto, FECHA perdido, etc.


def _parse_group(tokens: list[Token], i: int) -> tuple[Node | None, int]:
    atoms: list[Node] = []
    no, i = _parse_atom(tokens, i)
    if no is not None:
        atoms.append(no)
    while i < len(tokens) and tokens[i].tipo is TipoToken.OR:
        i += 1
        if i >= len(tokens) or tokens[i].tipo is TipoToken.FECHA:
            break
        no, i = _parse_atom(tokens, i)
        if no is not None:
            atoms.append(no)
    if not atoms:
        return None, i
    return (atoms[0] if len(atoms) == 1 else ("or", atoms)), i


def _parse_expr(tokens: list[Token], i: int) -> tuple[Node | None, int]:
    grupos: list[Node] = []
    while i < len(tokens) and tokens[i].tipo is not TipoToken.FECHA:
        if tokens[i].tipo is TipoToken.AND:
            i += 1
            continue
        no, i = _parse_group(tokens, i)
        if no is not None:
            grupos.append(no)
    if not grupos:
        return None, i
    return (grupos[0] if len(grupos) == 1 else ("and", grupos)), i


def _conta_termos(no: Node | None) -> int:
    if no is None:
        return 0
    if no[0] == "term":
        return 0 if no[3] else 1
    if no[0] in ("and", "or"):
        return sum(_conta_termos(f) for f in no[1])
    return 0


@dataclass(slots=True)
class Alvo:
    """Item normalizado para casamento."""

    titulo: str
    texto: str  # título + resumo normalizados
    url: str
    host: str
    publicado: date | None


def alvo_de(titulo: str, resumo: str, url: str, publicado_em: datetime | None) -> Alvo:
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    pub = publicado_em.astimezone(UTC).date() if publicado_em else None
    return Alvo(titulo=normalizar(titulo), texto=normalizar(f"{titulo} {resumo}"), url=url.lower(), host=host, publicado=pub)


def _parse_date(v: str) -> date | None:
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


@dataclass(slots=True)
class Matcher:
    query: str
    modo: Literal["termos", "estrito"] = "termos"
    arvore: Node | None = None
    tem_termos: bool = False
    casados: list[str] = field(default_factory=list)

    def casar(self, alvo: Alvo) -> list[str]:
        """Rótulos dos termos que casaram; lista vazia = não casou."""
        if not self.tem_termos or self.arvore is None:
            return []
        self.casados = []
        return list(dict.fromkeys(self.casados)) if self._eval(self.arvore, alvo) else []

    def _op(self, chave: str, valor: str, negado: bool, a: Alvo) -> bool:
        v = valor.lower()
        if chave == "site":
            if self.modo == "termos":
                return True
            dom = re.sub(r"^https?://", "", v).split("/", 1)[0].removeprefix("www.")
            ok = a.host == dom or a.host.endswith("." + dom)
            return (not ok) if negado else ok
        if chave in ("after", "since", "before", "until"):
            d = _parse_date(v)
            if d is None or a.publicado is None:
                return True  # sem data confiável, não restringe
            # No Radar after:/before: são INCLUSIVOS (o analista costuma usar a data de hoje); until: é exclusivo como no X.
            if chave in ("after", "since"):
                return a.publicado >= d
            if chave == "before":
                return a.publicado <= d
            return a.publicado < d  # until
        if chave == "intitle":
            ok = normalizar(v) in a.titulo
        elif chave == "intext":
            ok = normalizar(v) in a.texto
        elif chave == "inurl":
            ok = v in a.url
        elif chave == "filetype":
            ok = urlsplit(a.url).path.endswith("." + v.lstrip("."))
        else:
            return True  # filtros de motor (is:, has:, lang:, from:, to:, min_*…) não se aplicam a feeds
        return (not ok) if negado else ok

    def _eval(self, no: Node, a: Alvo) -> bool:
        tipo = no[0]
        if tipo == "true":
            return True
        if tipo == "term":
            _, rotulo, rx, negado = no
            achou = rx.search(a.texto) is not None
            if achou and not negado:
                self.casados.append(rotulo)
            return (not achou) if negado else achou
        if tipo == "op":
            return self._op(no[1], no[2], no[3], a)
        if tipo == "and":
            return all(self._eval(f, a) for f in no[1])
        if tipo == "or":
            # avalia todos para registrar todos os termos casados
            resultados = [self._eval(f, a) for f in no[1]]
            return any(resultados)
        return True


def compilar(query: str, modo: str = "termos") -> Matcher:
    tokens, _ = tokenizar(query)
    tokens = [t for t in tokens if not (t.tipo is TipoToken.OPERADOR and t.chave not in OPERADORES_CHAVE | OPERADORES_X_CHAVE)]
    arvore, _ = _parse_expr(tokens, 0)
    m = Matcher(query=query, modo="estrito" if modo == "estrito" else "termos", arvore=arvore)
    m.tem_termos = _conta_termos(arvore) > 0
    return m


# ------------------------------------------------------------------ coleta
def _sha(item: ItemFeed) -> str:
    return hashlib.sha256(f"{item.url}\n{item.titulo}\n{item.resumo}".encode("utf-8", "replace")).hexdigest()


def inserir_itens(session: Session, fonte: Fonte, itens: list[ItemFeed]) -> list[FonteItem]:
    """Grava só os itens ainda não vistos para a fonte. Não faz commit."""
    assert fonte.id is not None
    urls = [i.url for i in itens]
    if not urls:
        return []
    existentes = set(session.exec(select(FonteItem.url).where(FonteItem.fonte_id == fonte.id, col(FonteItem.url).in_(urls))).all())
    novos: list[FonteItem] = []
    for i in itens:
        if i.url in existentes:
            continue
        existentes.add(i.url)
        fi = FonteItem(fonte_id=fonte.id, url=i.url, titulo=i.titulo, resumo=i.resumo, publicado_em=i.publicado_em, sha256=_sha(i), midias=json.dumps(i.midias))
        session.add(fi)
        novos.append(fi)
    return novos


async def atualizar_fonte(session: Session, scraper: EthicalScraper, fonte: Fonte) -> tuple[list[FonteItem], str | None]:
    """Busca o feed (scraper ético), grava os itens novos e atualiza o status da fonte. Faz commit."""
    res = await scraper.buscar(fonte.url, respeitar_robots=fonte.respeitar_robots)
    return _processar_resultado(session, fonte, res.status, res.html, res.erro)


def _processar_resultado(session: Session, fonte: Fonte, status: int, corpo: str, erro: str | None) -> tuple[list[FonteItem], str | None]:
    fonte.ultima_coleta = agora()
    fonte.ultimo_status = status
    novos: list[FonteItem] = []
    if erro is None and 200 <= status < 300:
        try:
            itens = _itens_pagina(fonte, corpo) if getattr(fonte, "tipo", "feed") == "pagina" else parse_feed(corpo)
            novos = inserir_itens(session, fonte, itens)
            session.flush()
            fonte.itens_total = session.exec(select(func.count(FonteItem.id)).where(FonteItem.fonte_id == fonte.id)).one()
            fonte.ultimo_erro = ""
        except ValueError as exc:
            erro = str(exc)
    fonte.novos_ultima = len(novos)
    if erro:
        fonte.ultimo_erro = erro
    session.add(fonte)
    session.commit()
    for n in novos:
        session.refresh(n)
    return novos, erro


def _itens_pagina(fonte: Fonte, corpo: str) -> list[ItemFeed]:
    """Fonte do tipo página: extrai links de matérias, registra o hash do conteúdo e adota o RSS se a página anunciar um."""
    url_pagina = fonte.url
    itens = parse_pagina(corpo, url_pagina)
    novo_hash = hash_conteudo(corpo)
    if novo_hash != (fonte.conteudo_hash or ""):
        fonte.conteudo_hash = novo_hash
        fonte.ultima_mudanca = agora()
    feed = descobrir_feed(corpo, url_pagina)
    if feed and feed != url_pagina:
        fonte.tipo = "feed"
        fonte.url = feed
        logger.info("página anuncia RSS: fonte convertida em feed", extra={"dados": {"fonte": fonte.id, "pagina": url_pagina, "feed": feed}})
    return itens


def _monitores_ativos(session: Session) -> list[Monitor]:
    return list(session.exec(select(Monitor).where(Monitor.ativo == True, col(Monitor.tipo).in_(["query", "hashtag"]))).all())  # noqa: E712


def _fontes_por_id(session: Session) -> dict[int, Fonte]:
    return {f.id: f for f in session.exec(select(Fonte)).all() if f.id is not None}


def casar_itens(session: Session, monitores: list[Monitor], itens: list[FonteItem], origem: str = "radar") -> dict[int, list[MonitorHit]]:
    """Casa os itens com cada monitor; cria hits novos (único por monitor+URL). Faz commit."""
    if not itens or not monitores:
        return {}
    fontes = _fontes_por_id(session)
    alvos = [(it, alvo_de(it.titulo, it.resumo, it.url, it.publicado_em)) for it in itens]
    urls = [it.url for it in itens]
    por_monitor: dict[int, list[MonitorHit]] = {}
    for mon in monitores:
        assert mon.id is not None
        matcher = compilar(mon.query, getattr(mon, "radar_modo", "termos"))
        if not matcher.tem_termos:
            continue
        existentes = set(session.exec(select(MonitorHit.url).where(MonitorHit.monitor_id == mon.id, col(MonitorHit.url).in_(urls))).all())
        for it, alvo in alvos:
            if it.url in existentes:
                continue
            termos = matcher.casar(alvo)
            if not termos:
                continue
            existentes.add(it.url)
            f = fontes.get(it.fonte_id)
            hit = MonitorHit(
                monitor_id=mon.id,
                item_id=it.id,
                fonte_id=it.fonte_id,
                fonte_nome=f.nome if f else "",
                url=it.url,
                titulo=it.titulo,
                resumo=it.resumo[:600],
                publicado_em=it.publicado_em,
                termos=" | ".join(termos)[:300],
                origem=origem,
            )
            session.add(hit)
            por_monitor.setdefault(mon.id, []).append(hit)
    session.commit()
    for hits in por_monitor.values():
        for h in hits:
            session.refresh(h)
    if por_monitor:
        try:  # assistente de IA (só com iaAtivo; dedupe por URL dentro do pipeline)
            from app.services.ia import pipeline

            pipeline.enfileirar_hits(session, por_monitor, monitores)
        except Exception:  # a fila nunca derruba o casamento
            logger.exception("falha ao enfileirar hits para a IA")
    return por_monitor


def casar_monitor_cache(session: Session, mon: Monitor, desde: datetime | None = None, dias_padrao: int = 7, limite: int = 3000) -> list[MonitorHit]:
    """Casa um monitor com os itens já em cache (coletados desde `desde`, ou nos últimos N dias)."""
    if desde is not None and desde.tzinfo is None:  # datetimes lidos do SQLite podem voltar sem fuso
        desde = desde.replace(tzinfo=UTC)
    inicio = desde or (agora() - timedelta(days=dias_padrao))
    itens = list(
        session.exec(select(FonteItem).where(FonteItem.coletado_em >= inicio).order_by(col(FonteItem.coletado_em).desc()).limit(limite)).all()
    )
    return casar_itens(session, [mon], itens, origem="execucao").get(mon.id or -1, [])


def hit_resumo(h: MonitorHit) -> dict[str, Any]:
    return {
        "id": h.id,
        "titulo": h.titulo,
        "url": h.url,
        "fonte": h.fonte_nome,
        "publicado_em": h.publicado_em.isoformat() if h.publicado_em else None,
        "termos": h.termos,
    }


async def _alertar(mon: Monitor, hits: list[MonitorHit], session: Session | None = None) -> str:
    if session is not None:
        try:
            from app.models.alerta import Alerta
            from app.services.alertas_db import registrar_sync

            registrar_sync(
                session,
                Alerta(
                    tipo="radar",
                    severidade="media",
                    titulo=f"{mon.nome}: {len(hits)} novo(s) resultado(s)",
                    resumo="; ".join(h.titulo[:80] for h in hits[:5]),
                    url=hits[0].url if hits else "",
                    monitor_id=mon.id,
                ),
            )
        except Exception:  # inbox nunca derruba o ciclo
            logger.exception("falha ao gravar alerta do radar")
    evento = {
        "tipo": "radar",
        "monitor_id": mon.id,
        "nome": mon.nome,
        "query": mon.query,
        "novos_hits": len(hits),
        "hits": [hit_resumo(h) for h in hits[:50]],
        "executado_em": agora().isoformat(),
    }
    return await alerts.disparar(mon.canal_alerta, evento, mon.webhook_url)


def _suprimir_alertas_brutos() -> bool:
    """Com o assistente ligado, o alerta "N novos resultados" dá lugar ao cartão triado (preferência iaSuprimirAlertasBrutos)."""
    try:
        from app.routers.settings import carregar

        prefs = carregar().preferencias
        return bool(prefs.iaAtivo and prefs.iaSuprimirAlertasBrutos)
    except Exception:
        return False


async def ciclo(session: Session, scraper: EthicalScraper, apenas_fonte: Fonte | None = None) -> dict[str, Any]:
    """Um ciclo do Radar: atualiza as fontes ativas, casa os itens novos com todos os monitores ativos, alerta."""
    global ULTIMO_CICLO
    t0 = time.monotonic()
    fontes = [apenas_fonte] if apenas_fonte else list(session.exec(select(Fonte).where(Fonte.ativa == True)).all())  # noqa: E712
    if apenas_fonte is None:
        fontes = [f for f in fontes if fonte_devida(f, agora())]  # páginas/feeds com intervalo próprio
    # as buscas correm em paralelo pela fila do scraper (rate-limit por domínio); o banco é usado em sequência
    respostas = await asyncio.gather(*(scraper.buscar(f.url, respeitar_robots=f.respeitar_robots) for f in fontes))
    novos: list[FonteItem] = []
    relatorio_fontes: list[dict[str, Any]] = []
    for f, r in zip(fontes, respostas, strict=True):
        itens, erro = _processar_resultado(session, f, r.status, r.html, r.erro)
        novos += itens
        relatorio_fontes.append({"id": f.id, "nome": f.nome, "status": r.status, "novos": len(itens), "erro": erro})
    monitores = _monitores_ativos(session)
    por_monitor = casar_itens(session, monitores, novos)
    suprimir = _suprimir_alertas_brutos()
    alertas = 0
    for mon in monitores:
        hits = por_monitor.get(mon.id or -1, [])
        if hits and not (suprimir and getattr(mon, "ia", True)):
            await _alertar(mon, hits, session)
            alertas += 1
    resumo = {
        "executado_em": agora().isoformat(),
        "duracao_s": round(time.monotonic() - t0, 2),
        "fontes": relatorio_fontes,
        "itens_novos": len(novos),
        "monitores_avaliados": len(monitores),
        "hits_por_monitor": {str(mid): len(h) for mid, h in por_monitor.items()},
        "hits_novos": sum(len(h) for h in por_monitor.values()),
        "alertas": alertas,
    }
    if apenas_fonte is None:
        ULTIMO_CICLO = resumo
    logger.info("ciclo do radar", extra={"dados": {k: v for k, v in resumo.items() if k != "fontes"}})
    return resumo


# ------------------------------------------------------------------ fontes automáticas para hashtags
def url_mastodon_tag(tag: str, instancia: str = "mastodon.social") -> str:
    """Feed público de uma hashtag no Mastodon (aceita acentos; sem publicações o servidor responde 404)."""
    from urllib.parse import quote

    limpa = tag.strip().lstrip("#").replace(" ", "")
    return f"https://{instancia}/tags/{quote(limpa, safe='')}.rss"


def garantir_fonte_hashtag(session: Session, tag: str) -> Fonte:
    """Cria (uma vez) a fonte Mastodon da hashtag para que monitores de hashtag tenham uma fonte real."""
    url = url_mastodon_tag(tag)
    f = session.exec(select(Fonte).where(Fonte.url == url)).first()
    if f is None:
        f = Fonte(nome=f"Mastodon — {tag.strip() if tag.strip().startswith('#') else '#' + tag.strip()} (auto)", url=url, categoria="rede")
        session.add(f)
        session.commit()
        session.refresh(f)
    return f


def sincronizar_fontes_hashtags(session: Session) -> int:
    """Garante a fonte Mastodon de cada monitor de hashtag ativo (idempotente). Retorna quantas criou."""
    antes = session.exec(select(func.count(Fonte.id))).one()
    for mon in session.exec(select(Monitor).where(Monitor.ativo == True, Monitor.tipo == "hashtag")).all():  # noqa: E712
        garantir_fonte_hashtag(session, mon.query)
    return session.exec(select(func.count(Fonte.id))).one() - antes


def contagens_hits(session: Session) -> dict[int, tuple[int, int]]:
    """{monitor_id: (total, não lidos)}."""
    rows = session.exec(
        select(MonitorHit.monitor_id, func.count(MonitorHit.id), func.sum(func.iif(MonitorHit.lido == False, 1, 0))).group_by(MonitorHit.monitor_id)  # noqa: E712
    ).all()
    return {mid: (int(total), int(nao_lidos or 0)) for mid, total, nao_lidos in rows}
