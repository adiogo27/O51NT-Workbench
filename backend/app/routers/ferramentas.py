"""Ferramentas OSINT do servidor (lista de permissão, sem shell, com auditoria)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db import get_session
from app.middleware_auth import acesso_local_direto
from app.models.auth import Usuario
from app.routers.auth import usuario_atual
from app.services import ferramentas as svc

router = APIRouter(prefix="/api/ferramentas", tags=["ferramentas"])


class ExecutarIn(BaseModel):
    ferramenta: str = Field(min_length=1, max_length=40)
    alvo: str = Field(min_length=1, max_length=2000)
    por: str | None = Field(default=None, max_length=120)  # ex.: "openclaw:pesquisador"


class ExecucaoOut(BaseModel):
    id: int
    ferramenta: str
    alvo: str
    solicitante: str
    ok: bool
    duracao_ms: int
    resumo: str
    criado_em: datetime


def _sensiveis() -> bool:
    from app.routers.settings import carregar

    return bool(carregar().preferencias.ferramentasSensiveisAtivas)


@router.get("")
async def listar() -> dict[str, Any]:
    cat = svc.catalogo(_sensiveis())
    return {"ferramentas": cat, "instaladas": sum(1 for f in cat if f["instalada"]), "sensiveis_ativas": _sensiveis()}


@router.post("/executar")
async def executar(dados: ExecutarIn, usuario: Usuario = Depends(usuario_atual), session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        r = await svc.executar(session, dados.ferramenta, dados.alvo, solicitante=(dados.por or usuario.email or "painel"), sensiveis_ativas=_sensiveis())
    except svc.ErroFerramenta as exc:
        raise HTTPException(exc.status, exc.detalhe) from exc
    return {"id": r.id, "ferramenta": r.ferramenta, "alvo": r.alvo, "comando": r.comando, "ok": r.ok, "codigo": r.codigo, "saida": r.saida, "truncada": r.truncada, "duracao_ms": r.duracao_ms, "erro": r.erro}


@router.get("/executar")
async def executar_local(request: Request, ferramenta: str = Query(min_length=1, max_length=40), alvo: str = Query(min_length=1, max_length=2000), por: str = Query(default="openclaw", max_length=120), session: Session = Depends(get_session)) -> dict[str, Any]:
    """Variante por GET, SÓ para processos locais (o agent `pesquisador` do OpenClaw só consegue fazer GET). Via Caddy → 405."""
    if not acesso_local_direto(request.scope):
        raise HTTPException(405, "execução por GET só é aceita de processos locais; use POST")
    try:
        r = await svc.executar(session, ferramenta, alvo, solicitante=por, sensiveis_ativas=_sensiveis())
    except svc.ErroFerramenta as exc:
        raise HTTPException(exc.status, exc.detalhe) from exc
    return {"id": r.id, "ferramenta": r.ferramenta, "alvo": r.alvo, "ok": r.ok, "codigo": r.codigo, "saida": r.saida, "truncada": r.truncada, "duracao_ms": r.duracao_ms, "erro": r.erro}


@router.get("/historico", response_model=list[ExecucaoOut])
async def historico(limit: int = Query(default=50, ge=1, le=500), session: Session = Depends(get_session)) -> list[ExecucaoOut]:
    return [ExecucaoOut.model_validate(e, from_attributes=True) for e in svc.historico(session, limit)]
