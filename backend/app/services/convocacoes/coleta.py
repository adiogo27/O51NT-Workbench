"""Ciclo do coletor de convocações: fontes → candidatos (posts com imagem) → download → análise → persistência → alertas.

Fontes (tabela `fonte_convocacao`): bluesky_busca (API pública), telegram_canal (t.me/s/<canal>), searxng_imagens (dorks na
categoria `images` do SearXNG local) e feed_midia (itens de feed do Radar que trazem <enclosure>/<media:content>).
Orçamento por ciclo (`convocacoesMaxImagensCiclo`) protege CPU/RAM; dedup por post_url/sha256/pHash evita reanálise.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, col, select

from app.models._base import agora
from app.models.convocacao import Deteccao, DeteccaoOcorrencia, FonteConvocacao
from app.models.radar import Fonte, FonteItem
from app.models.settings import Preferencias
from app.services.convocacoes import bluesky, telegram
from app.services.convocacoes.analisador import Analisador, Entrada
from app.services.convocacoes.bluesky import PostCandidato
from app.services.convocacoes.persistencia import carregar_referencias, monitores_compilados, registrar_analise
from app.services.scraper import EthicalScraper

logger = logging.getLogger("o51nt.convocacoes.coleta")

ULTIMO_CICLO: dict[str, Any] | None = None
TIPOS_FONTE = ("bluesky_busca", "telegram_canal", "searxng_imagens", "feed_midia")
_CANAL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


def validar_fonte(tipo: str, parametro: str) -> None:
    if tipo not in TIPOS_FONTE:
        raise HTTPException(422, f"tipo inválido: {tipo}")
    p = (parametro or "").strip()
    if tipo == "feed_midia":
        return
    if not p:
        raise HTTPException(422, "parametro obrigatório para este tipo de fonte")
    if tipo == "telegram_canal" and not _CANAL_RE.match(telegram.normalizar_canal(p)):
        raise HTTPException(422, "canal do Telegram inválido (use @canal ou https://t.me/canal)")


def normalizar_parametro(tipo: str, parametro: str) -> str:
    p = " ".join((parametro or "").split())
    if tipo == "telegram_canal":
        return telegram.normalizar_canal(p)
    return p


def _prefs() -> Preferencias:
    from app.routers.settings import carregar

    return carregar().preferencias


# ------------------------------------------------------------------ coleta por fonte
async def coletar_fonte(scraper: EthicalScraper, searxng, fonte: FonteConvocacao, limite: int = 50, session: Session | None = None) -> tuple[list[PostCandidato], int, str | None, bool]:  # noqa: ANN001
    """(candidatos, http_status, erro, robots_permite). Não grava nada."""
    if fonte.tipo == "bluesky_busca":
        desde = fonte.ultima_coleta - timedelta(hours=1) if fonte.ultima_coleta else None
        if desde is not None and desde.tzinfo is None:
            desde = desde.replace(tzinfo=UTC)
        url = bluesky.url_busca(fonte.parametro, limite=limite, desde=desde)
        robots_ok = await scraper.robots.permitido(url)
        res = await scraper.buscar(url, respeitar_robots=fonte.respeitar_robots)
        if not res.ok:
            return [], res.status, res.erro or f"HTTP {res.status}", robots_ok
        try:
            cands, _cursor = bluesky.parse_busca(res.html)
        except ValueError as exc:
            return [], res.status, f"JSON inválido: {exc}", robots_ok
        return cands, res.status, None, robots_ok

    if fonte.tipo == "telegram_canal":
        url = telegram.url_canal(fonte.parametro)
        robots_ok = await scraper.robots.permitido(url)
        res = await scraper.buscar(url, respeitar_robots=fonte.respeitar_robots)
        if not res.ok:
            return [], res.status, res.erro or f"HTTP {res.status}", robots_ok
        canal = telegram.parse_canal(res.html, fonte.parametro)
        if not canal.posts and "tgme_channel_info" not in res.html:
            return [], res.status, "canal sem pré-visualização pública (privado ou inexistente)", robots_ok
        return canal.posts[-limite:], res.status, None, robots_ok

    if fonte.tipo == "searxng_imagens":
        if searxng is None:
            return [], 0, "SearXNG indisponível", True
        from app.services.searxng_client import ENGINES_IMAGENS, SearxngIndisponivel

        try:
            res = await searxng.buscar(fonte.parametro, ENGINES_IMAGENS, categorias="images")
        except SearxngIndisponivel as exc:
            return [], 0, str(exc), True
        if not res.ok:
            return [], res.status, res.erro, True
        cands: list[PostCandidato] = []
        for r in res.resultados:
            img = r.get("img_src") or r.get("thumbnail_src")
            if not img:
                continue
            cands.append(
                PostCandidato(
                    post_url=r["url"], plataforma=_plataforma_url(r["url"]), texto=f"{r.get('titulo', '')}\n{r.get('content', '')}".strip(),
                    publicado_em=_data(r.get("publishedDate")), imagens=[img], miniaturas=[r.get("thumbnail_src") or img], extra={"engines": r.get("engines")},
                )
            )
        return cands[:limite], res.status, None, True

    if fonte.tipo == "feed_midia":
        if session is None:
            return [], 200, None, True
        desde = fonte.ultima_coleta or (agora() - timedelta(days=2))
        if desde.tzinfo is None:
            desde = desde.replace(tzinfo=UTC)
        itens = session.exec(select(FonteItem).where(FonteItem.coletado_em >= desde, FonteItem.midias != "[]").order_by(col(FonteItem.coletado_em).desc()).limit(limite)).all()
        return candidatos_de_feed(session, list(itens)), 200, None, True
    return [], 0, f"tipo desconhecido: {fonte.tipo}", True


def _plataforma_url(url: str) -> str:
    from app.services.convocacoes.resolver import plataforma_de

    return plataforma_de(url)


def _data(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def candidatos_de_feed(session: Session, itens: list[FonteItem]) -> list[PostCandidato]:
    nomes = {f.id: f for f in session.exec(select(Fonte)).all()}
    out: list[PostCandidato] = []
    for it in itens:
        try:
            midias = json.loads(it.midias or "[]")
        except ValueError:
            midias = []
        if not midias:
            continue
        f = nomes.get(it.fonte_id)
        out.append(
            PostCandidato(
                post_url=it.url, plataforma="mastodon" if (f and "mastodon" in f.url) else "web", autor=f.nome if f else "",
                texto=f"{it.titulo}\n{it.resumo}".strip(), publicado_em=it.publicado_em, imagens=midias[:3], miniaturas=midias[:3],
                extra={"fonte_id": it.fonte_id, "imprensa": bool(f and f.categoria == "imprensa")},
            )
        )
    return out


# ------------------------------------------------------------------ processamento
async def processar_candidatos(session: Session, scraper: EthicalScraper, analisador: Analisador, candidatos: list[PostCandidato], origem: str, prefs: Preferencias, orcamento: int, fonte: FonteConvocacao | None = None) -> dict[str, int]:
    """Baixa e analisa até `orcamento` imagens novas. Retorna contadores."""
    stats = {"candidatos": len(candidatos), "pulados": 0, "sem_imagem": 0, "falha_download": 0, "analisados": 0, "novos": 0, "ocorrencias": 0, "alertas": 0}
    if not candidatos:
        return stats
    urls = [c.post_url for c in candidatos]
    vistos = set(session.exec(select(Deteccao.post_url).where(col(Deteccao.post_url).in_(urls))).all())
    vistos |= set(session.exec(select(DeteccaoOcorrencia.post_url).where(col(DeteccaoOcorrencia.post_url).in_(urls))).all())
    refs = carregar_referencias(session)
    mons = monitores_compilados(session)
    for c in candidatos:
        if stats["analisados"] >= orcamento:
            break
        if c.post_url in vistos:
            stats["pulados"] += 1
            continue
        vistos.add(c.post_url)
        if not c.imagens:
            # sem imagem: só vale a pena se o texto já parecer convocação (evita gravar todo post de texto)
            from app.services.convocacoes import lexico_mobilizacao as lexico

            if lexico.avaliar(c.texto_completo).score < 40:
                stats["sem_imagem"] += 1
                continue
            entrada = Entrada(texto_post=c.texto_completo, post_url=c.post_url, plataforma=c.plataforma, publicado_em=c.publicado_em, autor=c.autor, host_imprensa=bool(c.extra.get("imprensa")))
        else:
            dados: bytes | None = None
            img_url = ""
            for u in (c.imagens[0], *(c.miniaturas[:1] if c.miniaturas and c.miniaturas[0] != c.imagens[0] else [])):
                rb = await scraper.buscar_bytes(u, respeitar_robots=fonte.respeitar_robots if fonte else True)
                if rb.ok and (rb.mime.startswith("image/") or not rb.mime):
                    dados, img_url = rb.conteudo, u
                    break
            if dados is None:
                stats["falha_download"] += 1
                continue
            entrada = Entrada(imagem=dados, texto_post=c.texto_completo, post_url=c.post_url, imagem_url=img_url, plataforma=c.plataforma, publicado_em=c.publicado_em, autor=c.autor, host_imprensa=bool(c.extra.get("imprensa")))
        try:
            an = await analisador.analisar(entrada, refs, mons)
        except ValueError as exc:
            logger.warning("imagem inválida", extra={"dados": {"url": c.post_url, "erro": str(exc)}})
            stats["falha_download"] += 1
            continue
        stats["analisados"] += 1
        reg = await registrar_analise(session, entrada, an, prefs, origem=origem, fonte_id=fonte.id if fonte else c.extra.get("fonte_id"))
        if reg.nova:
            stats["novos"] += 1
        if reg.ocorrencia is not None:
            stats["ocorrencias"] += 1
        if reg.alerta is not None:
            stats["alertas"] += 1
    return stats


async def ciclo(session: Session, scraper: EthicalScraper, analisador: Analisador, searxng=None, apenas_fonte: FonteConvocacao | None = None) -> dict[str, Any]:  # noqa: ANN001
    global ULTIMO_CICLO
    t0 = time.monotonic()
    prefs = _prefs()
    fontes = [apenas_fonte] if apenas_fonte else list(session.exec(select(FonteConvocacao).where(FonteConvocacao.ativa == True)).all())  # noqa: E712
    if apenas_fonte is None and prefs.convocacoesAnalisarFeeds and not any(f.tipo == "feed_midia" for f in fontes):
        virtual = session.exec(select(FonteConvocacao).where(FonteConvocacao.tipo == "feed_midia")).first()
        if virtual is None:
            virtual = FonteConvocacao(nome="Feeds do Radar com imagem (auto)", tipo="feed_midia", parametro="", rede_alvo="mastodon")
            session.add(virtual)
            session.commit()
            session.refresh(virtual)
        if virtual.ativa:
            fontes.append(virtual)
    orcamento = prefs.convocacoesMaxImagensCiclo
    relatorio: list[dict[str, Any]] = []
    totais = {"analisados": 0, "novos": 0, "ocorrencias": 0, "alertas": 0}
    for f in fontes:
        cands, status_http, erro, _robots = await coletar_fonte(scraper, searxng, f, session=session)
        f.ultimo_status = status_http
        f.ultimo_erro = erro or ""
        stats = {"candidatos": len(cands)}
        if erro is None and orcamento > 0:
            stats = await processar_candidatos(session, scraper, analisador, cands, origem=f.tipo.split("_")[0] if f.tipo != "feed_midia" else "feed", prefs=prefs, orcamento=orcamento, fonte=f)
            orcamento -= stats["analisados"]
            f.itens_total += stats["novos"]
            f.novos_ultima = stats["novos"]
            for k in totais:
                totais[k] += stats.get(k, 0)
        f.ultima_coleta = agora()
        session.add(f)
        session.commit()
        relatorio.append({"id": f.id, "nome": f.nome, "tipo": f.tipo, "status": status_http, "erro": erro, **stats})
    resumo = {"executado_em": agora().isoformat(), "duracao_s": round(time.monotonic() - t0, 2), "fontes": relatorio, "orcamento_restante": orcamento, **totais}
    if apenas_fonte is None:
        ULTIMO_CICLO = resumo
    logger.info("ciclo de convocações", extra={"dados": {k: v for k, v in resumo.items() if k != "fontes"}})
    return resumo
