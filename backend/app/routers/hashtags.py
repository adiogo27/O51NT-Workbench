from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.db import get_session
from app.models.hashtag import Hashtag, HashtagSnapshot
from app.models.monitor import Monitor
from app.services import hashtag_tracker, query_compose, radar, scheduler
from app.services.scraper import get_scraper

router = APIRouter(prefix="/api/hashtags", tags=["hashtags"])


class HashtagIn(BaseModel):
    tag: str = Field(min_length=2, max_length=120)
    rede: str = "x"
    contagem: int = 0
    fonte: str = "manual"


class HashtagPatch(BaseModel):
    contagem: int | None = None
    fonte: str | None = None


class HashtagOut(BaseModel):
    id: int
    tag: str
    chave_normalizada: str
    rede: str
    contagem: int
    primeira_vez: datetime
    ultima_vez: datetime
    fonte: str
    monitor_id: int | None


class SnapshotOut(BaseModel):
    id: int
    coletado_em: datetime
    contagem: int
    fonte: str
    origem_url: str
    sha256: str


class TrackIn(BaseModel):
    tag: str = Field(min_length=2, max_length=120)
    cron: str = "0 */3 * * *"
    canal_alerta: Literal["jsonl", "webhook", "nenhum"] = "jsonl"
    webhook_url: str | None = None


class ColetarIn(BaseModel):
    tag: str = Field(min_length=2, max_length=120)
    fontes: list[Literal["trends24", "onemilliontweetmap"]] = ["trends24"]


def queries_hashtag(tag: str) -> dict:
    t = hashtag_tracker.normalizar_tag(tag)
    q = f"(site:facebook.com OR site:instagram.com) {t}"  # literal do PDF
    return {"tag": t, "query": q, "deeplinks": query_compose.deeplinks(q)}


def _get(session: Session, hid: int) -> Hashtag:
    h = session.get(Hashtag, hid)
    if h is None:
        raise HTTPException(404, "Hashtag não encontrada")
    return h


@router.get("", response_model=list[HashtagOut])
async def listar(rede: str | None = None, session: Session = Depends(get_session)) -> list[Hashtag]:
    stmt = select(Hashtag)
    if rede:
        stmt = stmt.where(Hashtag.rede == rede)
    return list(session.exec(stmt.order_by(col(Hashtag.contagem).desc(), Hashtag.tag)).all())


@router.post("", response_model=HashtagOut, status_code=201)
async def criar(dados: HashtagIn, session: Session = Depends(get_session)) -> Hashtag:
    tag = hashtag_tracker.normalizar_tag(dados.tag)
    h = Hashtag(
        tag=tag,
        chave_normalizada=hashtag_tracker.chave_normalizada(tag),
        rede=dados.rede,
        contagem=dados.contagem,
        fonte=dados.fonte,
    )
    session.add(h)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Hashtag já cadastrada para essa rede") from exc
    session.refresh(h)
    return h


@router.get("/queries")
async def queries(tag: str) -> dict:
    return queries_hashtag(tag)


@router.patch("/{hid}", response_model=HashtagOut)
async def atualizar(hid: int, dados: HashtagPatch, session: Session = Depends(get_session)) -> Hashtag:
    h = _get(session, hid)
    for k, v in dados.model_dump(exclude_unset=True).items():
        setattr(h, k, v)
    session.add(h)
    session.commit()
    session.refresh(h)
    return h


@router.delete("/{hid}", status_code=204)
async def remover(hid: int, session: Session = Depends(get_session)) -> None:
    h = _get(session, hid)
    session.delete(h)  # snapshots removidos via ON DELETE CASCADE
    session.commit()


class VariantesOut(BaseModel):
    tag: str
    chave_normalizada: str
    variantes: list[HashtagOut]


@router.get("/{hid}/variants", response_model=VariantesOut)
async def listar_variantes(hid: int, session: Session = Depends(get_session)) -> VariantesOut:
    """Todas as formas (acentuadas ou não, qualquer caixa) que casam com a hashtag."""
    h = _get(session, hid)
    vs = hashtag_tracker.variantes(session, h.tag, h.rede)
    return VariantesOut(
        tag=h.tag,
        chave_normalizada=h.chave_normalizada,
        variantes=[HashtagOut.model_validate(v, from_attributes=True) for v in vs],
    )


@router.get("/{hid}/series", response_model=list[SnapshotOut])
async def serie(hid: int, session: Session = Depends(get_session)) -> list[HashtagSnapshot]:
    _get(session, hid)
    return list(
        session.exec(
            select(HashtagSnapshot).where(HashtagSnapshot.hashtag_id == hid).order_by(HashtagSnapshot.coletado_em)
        ).all()
    )


@router.post("/track", response_model=HashtagOut, status_code=201)
async def rastrear(dados: TrackIn, session: Session = Depends(get_session)) -> Hashtag:
    """Cadastra monitoramento periódico (scheduler da Fase 2, tipo 'hashtag')."""
    try:
        scheduler.validar_cron(dados.cron)
    except ValueError as exc:
        raise HTTPException(422, f"cron inválido: {exc}") from exc
    tag = hashtag_tracker.normalizar_tag(dados.tag)
    mon = Monitor(
        nome=f"Hashtag {tag}",
        query=tag,
        cron=dados.cron,
        canal_alerta=dados.canal_alerta,
        webhook_url=dados.webhook_url,
        tipo="hashtag",
        proxima_execucao=scheduler.proxima_execucao(dados.cron),
    )
    session.add(mon)
    session.commit()
    session.refresh(mon)
    scheduler.agendar(mon)
    radar.garantir_fonte_hashtag(session, tag)  # fonte Mastodon automática: o monitor passa a ter onde casar
    h = session.exec(select(Hashtag).where(Hashtag.tag == tag, Hashtag.rede == "x")).first()
    if h is None:
        h = Hashtag(tag=tag, chave_normalizada=hashtag_tracker.chave_normalizada(tag), rede="x", fonte="monitor")
    h.monitor_id = mon.id
    session.add(h)
    session.commit()
    session.refresh(h)
    return h


@router.post("/collect")
async def coletar_agora(dados: ColetarIn, session: Session = Depends(get_session)) -> dict:
    """Coleta imediata (scraping ético) nas fontes públicas do PDF."""
    return await hashtag_tracker.coletar(session, get_scraper(), dados.tag, list(dados.fontes))
