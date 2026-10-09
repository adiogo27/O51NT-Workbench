from __future__ import annotations

import csv
import io
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.db import get_session
from app.models.boletim import Perfil
from app.models.monitor import Monitor
from app.schemas.boletim import PerfilDeeplinksOut, PerfilIn, PerfilMonitorIn, PerfilOut, PerfilPatch
from app.schemas.monitor import MonitorOut
from app.services import boletim as svc
from app.services import alerts, query_compose, scheduler

router = APIRouter(prefix="/api/perfis", tags=["perfis"])


def _get(session: Session, perfil_id: int) -> Perfil:
    p = session.get(Perfil, perfil_id)
    if p is None:
        raise HTTPException(404, "Perfil não encontrado")
    return p


def _listar(session: Session, rede: str | None = None, categoria: str | None = None, ativo: bool | None = None) -> list[Perfil]:
    stmt = select(Perfil)
    if rede:
        stmt = stmt.where(Perfil.rede == rede)
    if categoria:
        stmt = stmt.where(Perfil.categoria == categoria)
    if ativo is not None:
        stmt = stmt.where(Perfil.ativo == ativo)
    return list(session.exec(stmt.order_by(Perfil.categoria, Perfil.rede, col(Perfil.rotulo), Perfil.handle)).all())


@router.get("", response_model=list[PerfilOut])
async def listar(rede: str | None = None, categoria: str | None = None, ativo: bool | None = None, session: Session = Depends(get_session)) -> list[Perfil]:
    return _listar(session, rede, categoria, ativo)


@router.post("", response_model=PerfilOut, status_code=201)
async def criar(dados: PerfilIn, session: Session = Depends(get_session)) -> Perfil:
    try:
        handle = svc.normalizar_handle(dados.rede, dados.handle)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # handles de rede social não distinguem caixa (PRFBrasil ≡ prfbrasil); a UniqueConstraint é só o backstop
    repetido = session.exec(select(Perfil).where(Perfil.rede == dados.rede, func.lower(Perfil.handle) == handle.lower())).first()
    if repetido is not None:
        raise HTTPException(409, "Perfil já cadastrado nessa rede")
    p = Perfil(
        rede=dados.rede,
        handle=handle,
        url=svc.url_perfil(dados.rede, handle),
        rotulo=dados.rotulo.strip(),
        categoria=dados.categoria,
        notas=dados.notas,
        ativo=dados.ativo,
    )
    session.add(p)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Perfil já cadastrado nessa rede") from exc
    session.refresh(p)
    return p


@router.get("/export")
async def exportar(formato: Literal["csv", "json"] = "csv", session: Session = Depends(get_session)) -> Response:
    rows = [PerfilOut.model_validate(p, from_attributes=True).model_dump(mode="json") for p in _listar(session)]
    if formato == "json":
        return Response(json.dumps(rows, ensure_ascii=False, indent=2), media_type="application/json", headers={"Content-Disposition": 'attachment; filename="perfis.json"'})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(PerfilOut.model_fields))
    w.writeheader()
    w.writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="perfis.csv"'})


@router.get("/{perfil_id}", response_model=PerfilOut)
async def obter(perfil_id: int, session: Session = Depends(get_session)) -> Perfil:
    return _get(session, perfil_id)


@router.patch("/{perfil_id}", response_model=PerfilOut)
async def atualizar(perfil_id: int, dados: PerfilPatch, session: Session = Depends(get_session)) -> Perfil:
    p = _get(session, perfil_id)
    for k, v in dados.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


@router.delete("/{perfil_id}", status_code=204)
async def remover(perfil_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_get(session, perfil_id))
    session.commit()


@router.get("/{perfil_id}/deeplinks", response_model=PerfilDeeplinksOut)
async def deeplinks(perfil_id: int, session: Session = Depends(get_session)) -> PerfilDeeplinksOut:
    p = _get(session, perfil_id)
    q = svc.query_mencoes(p, "google")
    qx = svc.query_mencoes(p, "x")
    extra = query_compose.deeplinks_extra(qx)
    return PerfilDeeplinksOut(
        perfil=p.url,
        query_mencoes=q,
        query_mencoes_x=qx,
        deeplinks=query_compose.deeplinks(q),
        deeplinks_x={"x": extra["x"], "google_news": query_compose.deeplinks_extra(q)["google_news"]},
    )


@router.post("/{perfil_id}/monitor", response_model=MonitorOut, status_code=201)
async def monitorar(perfil_id: int, dados: PerfilMonitorIn, session: Session = Depends(get_session)) -> Monitor:
    p = _get(session, perfil_id)
    try:
        scheduler.validar_cron(dados.cron)
    except ValueError as exc:
        raise HTTPException(422, f"cron inválido: {exc}") from exc
    if dados.canal_alerta == "telegram" and not alerts.telegram_configurado():
        raise HTTPException(422, alerts.TELEGRAM_NAO_CONFIGURADO)
    if dados.canal_alerta == "webhook" and not (dados.webhook_url or "").startswith(("http://", "https://")):
        raise HTTPException(422, "webhook_url obrigatório (http/https) para canal webhook")
    usar_x = dados.usar_x if dados.usar_x is not None else p.rede == "x"
    mon = Monitor(
        nome=f"Perfil: {p.rotulo or p.handle} ({p.rede})",
        query=svc.query_mencoes(p, "x" if usar_x else "google"),
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
    p.monitor_id = mon.id
    session.add(p)
    session.commit()
    return mon
