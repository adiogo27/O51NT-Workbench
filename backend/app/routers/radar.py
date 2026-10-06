from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.db import get_session
from app.models.boletim import BoletimItem
from app.models.monitor import Monitor
from app.models.radar import Fonte, FonteItem, MonitorHit
from app.schemas.boletim import BoletimItemOut
from app.schemas.radar import (
    FonteIn,
    FonteOut,
    FontePatch,
    FonteTesteIn,
    FonteTesteOut,
    HitBoletimIn,
    HitOut,
    HitPatch,
    ItemOut,
    RadarStatusOut,
)
from app.seed import CATALOGO_FONTES
from app.services import radar as svc
from app.services import scheduler
from app.services.scraper import get_scraper

router = APIRouter(prefix="/api/radar", tags=["radar"])


def _fonte(session: Session, fonte_id: int) -> Fonte:
    f = session.get(Fonte, fonte_id)
    if f is None:
        raise HTTPException(404, "Fonte não encontrada")
    return f


def _hit(session: Session, hit_id: int) -> MonitorHit:
    h = session.get(MonitorHit, hit_id)
    if h is None:
        raise HTTPException(404, "Hit não encontrado")
    return h


def hit_out(h: MonitorHit, nomes: dict[int, str]) -> HitOut:
    return HitOut.model_validate({**h.model_dump(), "monitor_nome": nomes.get(h.monitor_id, "")})


def listar_hits(
    session: Session, monitor_id: int | None = None, lidos: bool | None = None, desde: datetime | None = None, limit: int = 100
) -> list[HitOut]:
    stmt = select(MonitorHit)
    if monitor_id is not None:
        stmt = stmt.where(MonitorHit.monitor_id == monitor_id)
    if lidos is not None:
        stmt = stmt.where(MonitorHit.lido == lidos)
    if desde is not None:
        stmt = stmt.where(MonitorHit.encontrado_em >= desde)
    hits = session.exec(stmt.order_by(col(MonitorHit.encontrado_em).desc(), col(MonitorHit.id).desc()).limit(min(limit, 1000))).all()
    nomes = {m.id: m.nome for m in session.exec(select(Monitor)).all() if m.id is not None}
    return [hit_out(h, nomes) for h in hits]


# ------------------------------------------------------------------ status / ciclo
@router.get("/status", response_model=RadarStatusOut)
async def status(session: Session = Depends(get_session)) -> RadarStatusOut:
    from app.routers.settings import carregar

    prefs = carregar().preferencias
    job = scheduler.job_radar()
    contagens = svc.contagens_hits(session)
    return RadarStatusOut(
        ativo=prefs.radarAtivo,
        intervalo_min=prefs.radarIntervaloMin,
        agendado=job is not None,
        proximo_ciclo=job.next_run_time if job is not None else None,
        ultimo_ciclo=svc.ULTIMO_CICLO,
        fontes_ativas=session.exec(select(func.count(Fonte.id)).where(Fonte.ativa == True)).one(),  # noqa: E712
        fontes_total=session.exec(select(func.count(Fonte.id))).one(),
        monitores_ativos=session.exec(select(func.count(Monitor.id)).where(Monitor.ativo == True, col(Monitor.tipo).in_(["query", "hashtag"]))).one(),  # noqa: E712
        itens_total=session.exec(select(func.count(FonteItem.id))).one(),
        hits_total=sum(t for t, _ in contagens.values()),
        hits_novos=sum(n for _, n in contagens.values()),
    )


@router.post("/ciclo")
async def rodar_ciclo(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Atualiza todas as fontes ativas e casa os itens novos com todos os monitores ativos (agora)."""
    return await svc.ciclo(session, get_scraper())


# ------------------------------------------------------------------ fontes
@router.get("/fontes", response_model=list[FonteOut])
async def listar_fontes(session: Session = Depends(get_session)) -> list[Fonte]:
    return list(session.exec(select(Fonte).order_by(col(Fonte.ativa).desc(), Fonte.categoria, Fonte.nome)).all())


@router.get("/fontes/catalogo")
async def catalogo(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Fontes sugeridas (verificadas) + modelos (Google Alertas, Mastodon por hashtag)."""
    existentes = set(session.exec(select(Fonte.url)).all())
    return [{**c, "cadastrada": c["url"] in existentes} for c in CATALOGO_FONTES]


@router.post("/fontes", response_model=FonteOut, status_code=201)
async def criar_fonte(dados: FonteIn, session: Session = Depends(get_session)) -> Fonte:
    f = Fonte(**dados.model_dump())
    session.add(f)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Fonte já cadastrada (mesma URL)") from exc
    session.refresh(f)
    return f


@router.post("/fontes/testar", response_model=FonteTesteOut)
async def testar_fonte(dados: FonteTesteIn) -> FonteTesteOut:
    """Busca e interpreta o feed sem gravar nada (para o analista validar a URL)."""
    scraper = get_scraper()
    permite = await scraper.robots.permitido(dados.url)
    res = await scraper.buscar(dados.url, respeitar_robots=dados.respeitar_robots)
    if not res.ok:
        return FonteTesteOut(ok=False, status=res.status, erro=res.erro or f"HTTP {res.status}", robots_permite=permite, itens=0, amostra=[])
    try:
        itens = svc.parse_feed(res.html)
    except ValueError as exc:
        return FonteTesteOut(ok=False, status=res.status, erro=str(exc), robots_permite=permite, itens=0, amostra=[])
    amostra = [{"titulo": i.titulo, "url": i.url, "publicado_em": i.publicado_em.isoformat() if i.publicado_em else None} for i in itens[:5]]
    return FonteTesteOut(ok=True, status=res.status, erro=None, robots_permite=permite, itens=len(itens), amostra=amostra)


@router.get("/fontes/{fonte_id}", response_model=FonteOut)
async def obter_fonte(fonte_id: int, session: Session = Depends(get_session)) -> Fonte:
    return _fonte(session, fonte_id)


@router.patch("/fontes/{fonte_id}", response_model=FonteOut)
async def atualizar_fonte(fonte_id: int, dados: FontePatch, session: Session = Depends(get_session)) -> Fonte:
    f = _fonte(session, fonte_id)
    for k, v in dados.model_dump(exclude_unset=True).items():
        setattr(f, k, v)
    session.add(f)
    session.commit()
    session.refresh(f)
    return f


@router.delete("/fontes/{fonte_id}", status_code=204)
async def remover_fonte(fonte_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_fonte(session, fonte_id))
    session.commit()


@router.post("/fontes/{fonte_id}/coletar")
async def coletar_fonte(fonte_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Coleta só esta fonte e casa os itens novos com os monitores ativos."""
    f = _fonte(session, fonte_id)
    return await svc.ciclo(session, get_scraper(), apenas_fonte=f)


# ------------------------------------------------------------------ itens e hits
@router.get("/itens", response_model=list[ItemOut])
async def listar_itens(fonte_id: int | None = None, q: str | None = None, limit: int = Query(default=100, ge=1, le=1000), session: Session = Depends(get_session)) -> list[ItemOut]:
    stmt = select(FonteItem)
    if fonte_id is not None:
        stmt = stmt.where(FonteItem.fonte_id == fonte_id)
    itens = session.exec(stmt.order_by(col(FonteItem.coletado_em).desc(), col(FonteItem.id).desc()).limit(limit if not q else 2000)).all()
    if q:
        nq = svc.normalizar(q)
        itens = [i for i in itens if nq in svc.normalizar(f"{i.titulo} {i.resumo}")][:limit]
    nomes = {f.id: f.nome for f in session.exec(select(Fonte)).all() if f.id is not None}
    return [ItemOut.model_validate({**i.model_dump(), "fonte_nome": nomes.get(i.fonte_id, "")}) for i in itens]


@router.get("/hits", response_model=list[HitOut])
async def hits(
    monitor_id: int | None = None,
    lidos: bool | None = None,
    desde: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> list[HitOut]:
    return listar_hits(session, monitor_id, lidos, desde, limit)


@router.patch("/hits/{hit_id}", response_model=HitOut)
async def marcar_hit(hit_id: int, dados: HitPatch, session: Session = Depends(get_session)) -> HitOut:
    h = _hit(session, hit_id)
    h.lido = dados.lido
    session.add(h)
    session.commit()
    session.refresh(h)
    nomes = {m.id: m.nome for m in session.exec(select(Monitor)).all() if m.id is not None}
    return hit_out(h, nomes)


@router.post("/hits/marcar-todos")
async def marcar_todos(monitor_id: int | None = None, session: Session = Depends(get_session)) -> dict[str, int]:
    stmt = select(MonitorHit).where(MonitorHit.lido == False)  # noqa: E712
    if monitor_id is not None:
        stmt = stmt.where(MonitorHit.monitor_id == monitor_id)
    n = 0
    for h in session.exec(stmt).all():
        h.lido = True
        session.add(h)
        n += 1
    session.commit()
    return {"marcados": n}


@router.post("/hits/{hit_id}/boletim", response_model=BoletimItemOut, status_code=201)
async def hit_para_boletim(hit_id: int, dados: HitBoletimIn, session: Session = Depends(get_session)) -> BoletimItem:
    """Leva o hit para o boletim do dia (seção escolhida) e marca como lido."""
    h = _hit(session, hit_id)
    if h.boletim_item_id and session.get(BoletimItem, h.boletim_item_id) is not None:
        raise HTTPException(409, f"Hit já está no boletim (item #{h.boletim_item_id})")
    item = BoletimItem(
        data=dados.data or (h.publicado_em.date() if h.publicado_em else date.today()),
        secao=dados.secao,
        titulo=h.titulo[:300] or h.url,
        url=h.url,
        fonte=h.fonte_nome[:120],
        resumo=h.resumo[:3000],
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    h.boletim_item_id = item.id
    h.lido = True
    session.add(h)
    session.commit()
    return item
