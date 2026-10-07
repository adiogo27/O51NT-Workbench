from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select

from app.db import get_session
from app.models.alerta import Alerta
from app.schemas.alerta import AlertaOut, AlertaPatch
from app.services import alertas_db

router = APIRouter(prefix="/api/alertas", tags=["alertas"])


@router.get("", response_model=list[AlertaOut])
async def listar(
    lidos: bool | None = None,
    tipo: str | None = None,
    severidade: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> list[Alerta]:
    stmt = select(Alerta)
    if lidos is not None:
        stmt = stmt.where(Alerta.lido == lidos)
    if tipo:
        stmt = stmt.where(Alerta.tipo == tipo)
    if severidade:
        stmt = stmt.where(Alerta.severidade == severidade)
    return list(session.exec(stmt.order_by(col(Alerta.criado_em).desc(), col(Alerta.id).desc()).limit(limit)).all())


@router.get("/contagem")
async def contagem(session: Session = Depends(get_session)) -> dict[str, int]:
    return alertas_db.contagem_nao_lidos(session)


@router.patch("/{alerta_id}", response_model=AlertaOut)
async def marcar(alerta_id: int, dados: AlertaPatch, session: Session = Depends(get_session)) -> Alerta:
    a = session.get(Alerta, alerta_id)
    if a is None:
        raise HTTPException(404, "Alerta não encontrado")
    a.lido = dados.lido
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


@router.post("/marcar-todos")
async def marcar_todos(tipo: str | None = None, session: Session = Depends(get_session)) -> dict[str, int]:
    stmt = select(Alerta).where(Alerta.lido == False)  # noqa: E712
    if tipo:
        stmt = stmt.where(Alerta.tipo == tipo)
    n = 0
    for a in session.exec(stmt).all():
        a.lido = True
        session.add(a)
        n += 1
    session.commit()
    return {"marcados": n}


@router.delete("/{alerta_id}", status_code=204)
async def remover(alerta_id: int, session: Session = Depends(get_session)) -> None:
    a = session.get(Alerta, alerta_id)
    if a is None:
        raise HTTPException(404, "Alerta não encontrado")
    session.delete(a)
    session.commit()
