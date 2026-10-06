from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.db import get_session
from app.models.monitor import Monitor, MonitorRun
from app.schemas.monitor import MonitorIn, MonitorOut, MonitorPatch, MonitorRunOut
from app.services import radar, scheduler

router = APIRouter(prefix="/api/monitors", tags=["monitors"])


def run_out(r: MonitorRun) -> MonitorRunOut:
    assert r.id is not None
    return MonitorRunOut(
        id=r.id,
        monitor_id=r.monitor_id,
        executado_em=r.executado_em,
        status=r.status,
        deeplinks=json.loads(r.deeplinks_json or "{}"),
        resultado=json.loads(r.resultado_json or "{}"),
        log=r.log,
    )


def _validar(cron: str, canal: str, webhook_url: str | None) -> None:
    try:
        scheduler.validar_cron(cron)
    except ValueError as exc:
        raise HTTPException(422, f"cron inválido: {exc}") from exc
    if canal == "webhook" and not (webhook_url or "").startswith(("http://", "https://")):
        raise HTTPException(422, "webhook_url obrigatório (http/https) para canal webhook")


def _get(session: Session, monitor_id: int) -> Monitor:
    mon = session.get(Monitor, monitor_id)
    if mon is None:
        raise HTTPException(404, "Monitor não encontrado")
    return mon


@router.get("", response_model=list[MonitorOut])
async def listar(session: Session = Depends(get_session)) -> list[MonitorOut]:
    contagens = radar.contagens_hits(session)
    saida: list[MonitorOut] = []
    for m in session.exec(select(Monitor).order_by(col(Monitor.id).desc())).all():
        total, novos = contagens.get(m.id or -1, (0, 0))
        saida.append(MonitorOut.model_validate(m, from_attributes=True).model_copy(update={"hits_total": total, "hits_novos": novos}))
    return saida


@router.post("", response_model=MonitorOut, status_code=201)
async def criar(dados: MonitorIn, session: Session = Depends(get_session)) -> Monitor:
    _validar(dados.cron, dados.canal_alerta, dados.webhook_url)
    mon = Monitor(**dados.model_dump())
    mon.proxima_execucao = scheduler.proxima_execucao(mon.cron) if mon.ativo else None
    session.add(mon)
    session.commit()
    session.refresh(mon)
    scheduler.agendar(mon)
    if mon.tipo in ("query", "hashtag"):
        radar.casar_monitor_cache(session, mon)  # já nasce com os hits dos itens em cache (últimos 7 dias)
    return mon


@router.get("/{monitor_id}", response_model=MonitorOut)
async def obter(monitor_id: int, session: Session = Depends(get_session)) -> Monitor:
    return _get(session, monitor_id)


@router.patch("/{monitor_id}", response_model=MonitorOut)
async def atualizar(monitor_id: int, dados: MonitorPatch, session: Session = Depends(get_session)) -> Monitor:
    mon = _get(session, monitor_id)
    for k, v in dados.model_dump(exclude_unset=True).items():
        setattr(mon, k, v)
    _validar(mon.cron, mon.canal_alerta, mon.webhook_url)
    mon.proxima_execucao = scheduler.proxima_execucao(mon.cron) if mon.ativo else None
    session.add(mon)
    session.commit()
    session.refresh(mon)
    scheduler.agendar(mon)
    return mon


@router.delete("/{monitor_id}", status_code=204)
async def remover(monitor_id: int, session: Session = Depends(get_session)) -> None:
    mon = _get(session, monitor_id)
    session.delete(mon)  # execuções removidas via ON DELETE CASCADE
    session.commit()
    scheduler.desagendar(monitor_id)


@router.post("/{monitor_id}/run-now", response_model=MonitorRunOut)
async def executar_agora(monitor_id: int, session: Session = Depends(get_session)) -> MonitorRunOut:
    _get(session, monitor_id)
    run = await scheduler.executar_monitor(monitor_id)
    if run is None:
        raise HTTPException(404, "Monitor não encontrado")
    return run_out(run)


@router.get("/{monitor_id}/results", response_model=list[MonitorRunOut])
async def resultados(monitor_id: int, limit: int = 100, session: Session = Depends(get_session)) -> list[MonitorRunOut]:
    _get(session, monitor_id)
    rows = session.exec(
        select(MonitorRun)
        .where(MonitorRun.monitor_id == monitor_id)
        .order_by(col(MonitorRun.executado_em).desc(), col(MonitorRun.id).desc())
        .limit(min(limit, 1000))
    ).all()
    return [run_out(r) for r in rows]


@router.get("/{monitor_id}/hits")
async def hits_do_monitor(monitor_id: int, lidos: bool | None = None, limit: int = 100, session: Session = Depends(get_session)) -> list:
    """Resultados reais (hits do Radar) deste monitor, mais recentes primeiro."""
    from app.routers.radar import listar_hits

    _get(session, monitor_id)
    return listar_hits(session, monitor_id=monitor_id, lidos=lidos, limit=limit)
