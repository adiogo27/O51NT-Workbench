from __future__ import annotations

import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlmodel import Session, col, select

from app.db import get_session
from app.models._base import agora
from app.models.agenda import AgendaEvento
from app.models.monitor import Monitor
from app.schemas.agenda import (
    AgendaDiaOut,
    AgendaEventoIn,
    AgendaEventoOut,
    AgendaEventoPatch,
    AgendaMonitorIn,
    AgendaQueriesOut,
)
from app.schemas.monitor import MonitorOut
from app.services import agenda as svc
from app.services import query_compose, scheduler

router = APIRouter(prefix="/api/agenda", tags=["agenda"])


def evento_out(ev: AgendaEvento) -> AgendaEventoOut:
    assert ev.id is not None
    return AgendaEventoOut(
        id=ev.id,
        candidato=ev.candidato,
        partido=ev.partido,
        cargo=ev.cargo,
        titulo=ev.titulo,
        tipo=ev.tipo,
        data=ev.data,
        dia_semana=svc.dia_semana(ev.data),
        hora_inicio=ev.hora_inicio,
        hora_fim=ev.hora_fim,
        cidade=ev.cidade,
        uf=ev.uf,
        local=ev.local,
        rodovias=svc.rodovias_lista(ev),
        impacto_rodovia=ev.impacto_rodovia,
        descricao=ev.descricao,
        fonte_url=ev.fonte_url,
        status=ev.status,
        monitor_id=ev.monitor_id,
        criado_em=ev.criado_em,
        atualizado_em=ev.atualizado_em,
    )


def _get(session: Session, evento_id: int) -> AgendaEvento:
    ev = session.get(AgendaEvento, evento_id)
    if ev is None:
        raise HTTPException(404, "Evento não encontrado")
    return ev


def _listar(
    session: Session,
    de: date | None = None,
    ate: date | None = None,
    data: date | None = None,
    uf: str | None = None,
    candidato: str | None = None,
    tipo: str | None = None,
    status: str | None = None,
    impacto_rodovia: bool | None = None,
    limit: int = 500,
) -> list[AgendaEvento]:
    stmt = select(AgendaEvento)
    if data:
        stmt = stmt.where(AgendaEvento.data == data)
    if de:
        stmt = stmt.where(AgendaEvento.data >= de)
    if ate:
        stmt = stmt.where(AgendaEvento.data <= ate)
    if uf:
        stmt = stmt.where(AgendaEvento.uf == uf.upper())
    if candidato:
        stmt = stmt.where(col(AgendaEvento.candidato).ilike(f"%{candidato}%"))
    if tipo:
        stmt = stmt.where(AgendaEvento.tipo == tipo)
    if status:
        stmt = stmt.where(AgendaEvento.status == status)
    if impacto_rodovia is not None:
        stmt = stmt.where(AgendaEvento.impacto_rodovia == impacto_rodovia)
    stmt = stmt.order_by(AgendaEvento.data, col(AgendaEvento.hora_inicio).is_(None), AgendaEvento.hora_inicio, AgendaEvento.candidato)
    return list(session.exec(stmt.limit(min(limit, 5000))).all())


@router.get("", response_model=list[AgendaEventoOut])
async def listar(
    de: date | None = None,
    ate: date | None = None,
    data: date | None = None,
    uf: str | None = None,
    candidato: str | None = None,
    tipo: str | None = None,
    status: str | None = None,
    impacto_rodovia: bool | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    session: Session = Depends(get_session),
) -> list[AgendaEventoOut]:
    return [evento_out(e) for e in _listar(session, de, ate, data, uf, candidato, tipo, status, impacto_rodovia, limit)]


@router.post("", response_model=AgendaEventoOut, status_code=201)
async def criar(dados: AgendaEventoIn, session: Session = Depends(get_session)) -> AgendaEventoOut:
    campos = dados.model_dump()
    campos["rodovias"] = ",".join(dados.rodovias)
    ev = AgendaEvento(**campos)
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return evento_out(ev)


@router.get("/dia/{data}", response_model=AgendaDiaOut)
async def dia(data: date, session: Session = Depends(get_session)) -> AgendaDiaOut:
    """Agenda consolidada do dia, no formato do boletim (agrupada por candidato)."""
    eventos = [evento_out(e) for e in _listar(session, data=data)]
    por_candidato: dict[str, list[AgendaEventoOut]] = {}
    for e in eventos:
        por_candidato.setdefault(e.candidato, []).append(e)
    return AgendaDiaOut(
        data=data,
        dia_semana=svc.dia_semana(data),
        total=len(eventos),
        com_impacto_rodovia=sum(1 for e in eventos if e.impacto_rodovia),
        por_candidato=dict(sorted(por_candidato.items(), key=lambda kv: kv[0].lower())),
        eventos=eventos,
    )


@router.get("/export")
async def exportar(
    formato: Literal["csv", "json", "ics"] = "csv",
    de: date | None = None,
    ate: date | None = None,
    data: date | None = None,
    impacto_rodovia: bool | None = None,
    session: Session = Depends(get_session),
) -> Response:
    eventos = _listar(session, de, ate, data, impacto_rodovia=impacto_rodovia)
    sufixo = data.isoformat() if data else f"{de or 'inicio'}_{ate or 'fim'}"
    if formato == "json":
        corpo = json.dumps([evento_out(e).model_dump(mode="json") for e in eventos], ensure_ascii=False, indent=2)
        return Response(corpo, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="agenda_{sufixo}.json"'})
    if formato == "ics":
        return Response(
            svc.gerar_ics(eventos),
            media_type="text/calendar; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="agenda_{sufixo}.ics"'},
        )
    return Response(
        svc.gerar_csv(eventos),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="agenda_{sufixo}.csv"'},
    )


@router.get("/{evento_id}", response_model=AgendaEventoOut)
async def obter(evento_id: int, session: Session = Depends(get_session)) -> AgendaEventoOut:
    return evento_out(_get(session, evento_id))


@router.patch("/{evento_id}", response_model=AgendaEventoOut)
async def atualizar(evento_id: int, dados: AgendaEventoPatch, session: Session = Depends(get_session)) -> AgendaEventoOut:
    ev = _get(session, evento_id)
    campos = dados.model_dump(exclude_unset=True)
    if "rodovias" in campos:
        campos["rodovias"] = ",".join(campos["rodovias"] or [])
    for k, v in campos.items():
        setattr(ev, k, v)
    ev.atualizado_em = agora()
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return evento_out(ev)


@router.delete("/{evento_id}", status_code=204)
async def remover(evento_id: int, session: Session = Depends(get_session)) -> None:
    ev = _get(session, evento_id)
    session.delete(ev)
    session.commit()


@router.get("/{evento_id}/queries", response_model=AgendaQueriesOut)
async def queries(evento_id: int, session: Session = Depends(get_session)) -> AgendaQueriesOut:
    """Queries de monitoramento do evento (Google e X), cruzando cidade e rodovias da base DNIT."""
    ev = _get(session, evento_id)
    q = svc.montar_query(ev, "google")
    qx = svc.montar_query(ev, "x")
    return AgendaQueriesOut(
        evento_id=evento_id,
        query=q,
        query_x=qx,
        deeplinks=query_compose.deeplinks(q),
        deeplinks_x={"x": query_compose.deeplinks_extra(qx)["x"], "google_news": query_compose.deeplinks_extra(q)["google_news"]},
        termos_rodovia=svc.termos_rodovia(svc.rodovias_lista(ev)),
    )


@router.post("/{evento_id}/monitor", response_model=MonitorOut, status_code=201)
async def monitorar(evento_id: int, dados: AgendaMonitorIn, session: Session = Depends(get_session)) -> Monitor:
    """Cria um Monitor (Fase 2) com a query do evento; o id do monitor fica gravado no evento."""
    ev = _get(session, evento_id)
    try:
        scheduler.validar_cron(dados.cron)
    except ValueError as exc:
        raise HTTPException(422, f"cron inválido: {exc}") from exc
    if dados.canal_alerta == "webhook" and not (dados.webhook_url or "").startswith(("http://", "https://")):
        raise HTTPException(422, "webhook_url obrigatório (http/https) para canal webhook")
    mon = Monitor(
        nome=f"Agenda: {ev.candidato} — {ev.titulo} ({ev.data.isoformat()})",
        query=svc.montar_query(ev, "x" if dados.usar_x else "google"),
        cron=dados.cron,
        canal_alerta=dados.canal_alerta,
        webhook_url=dados.webhook_url,
        tipo="query",
        proxima_execucao=scheduler.proxima_execucao(dados.cron),
    )
    session.add(mon)
    session.commit()
    session.refresh(mon)
    scheduler.agendar(mon)
    ev.monitor_id = mon.id
    ev.atualizado_em = agora()
    session.add(ev)
    session.commit()
    return mon
