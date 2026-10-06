from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.db import get_session
from app.models.query import QueryHistory
from app.models.template import QueryTemplate
from app.schemas.query import (
    ComposeRequest,
    ComposeResponse,
    HistoryIn,
    HistoryOut,
    ProblemaOut,
    TemplateIn,
    TemplateOut,
    ValidateRequest,
    ValidateResponse,
)
from app.services import operators, query_compose, retention

router = APIRouter(prefix="/api/query", tags=["query-builder"])


def _problemas(lista: list[operators.Problema]) -> list[ProblemaOut]:
    return [ProblemaOut(codigo=p.codigo, mensagem=p.mensagem, posicao=p.posicao) for p in lista]


def template_out(t: QueryTemplate) -> TemplateOut:
    assert t.id is not None
    return TemplateOut(
        id=t.id,
        nome=t.nome,
        categoria=t.categoria,
        descricao=t.descricao,
        query=t.query,
        placeholders=[p for p in t.placeholders.split("|") if p],
        origem_pdf=t.origem_pdf,
        criado_em=t.criado_em,
    )


@router.post("/compose", response_model=ComposeResponse)
async def compose(req: ComposeRequest, session: Session = Depends(get_session)) -> ComposeResponse:
    template_query: str | None = None
    if req.template_id is not None:
        tpl = session.get(QueryTemplate, req.template_id)
        if tpl is None:
            raise HTTPException(404, "Template não encontrado")
        template_query = tpl.query
    query = query_compose.compor(req, template_query)
    res = operators.validar(query)
    return ComposeResponse(
        query=query,
        valida=res.valida,
        erros=_problemas(res.erros),
        avisos=_problemas(res.avisos),
        deeplinks=query_compose.deeplinks(query) if query else {},
        compatibilidade=query_compose.compatibilidade(res.operadores, query),
        deeplinks_extra=query_compose.deeplinks_extra(query) if query else {},
        compatibilidade_extra=query_compose.compatibilidade_extra(res.operadores, query),
        operadores_x=operators.operadores_x(query),
    )


@router.post("/validate", response_model=ValidateResponse)
async def validate(req: ValidateRequest) -> ValidateResponse:
    res = operators.validar(req.query)
    tem_query = bool(req.query.strip())
    return ValidateResponse(
        query=req.query,
        valida=res.valida,
        erros=_problemas(res.erros),
        avisos=_problemas(res.avisos),
        operadores=res.operadores,
        deeplinks=query_compose.deeplinks(req.query) if tem_query else {},
        compatibilidade=query_compose.compatibilidade(res.operadores, req.query),
        deeplinks_extra=query_compose.deeplinks_extra(req.query) if tem_query else {},
        compatibilidade_extra=query_compose.compatibilidade_extra(res.operadores, req.query),
        operadores_x=operators.operadores_x(req.query),
    )


@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(session: Session = Depends(get_session)) -> list[TemplateOut]:
    rows = session.exec(select(QueryTemplate).order_by(col(QueryTemplate.origem_pdf).desc(), QueryTemplate.id)).all()
    return [template_out(t) for t in rows]


@router.post("/templates", response_model=TemplateOut, status_code=201)
async def create_template(dados: TemplateIn, session: Session = Depends(get_session)) -> TemplateOut:
    tpl = QueryTemplate(
        nome=dados.nome.strip(),
        categoria=dados.categoria,
        descricao=dados.descricao,
        query=dados.query.strip(),
        placeholders="|".join(p for p in dados.placeholders if p),
        origem_pdf=False,
    )
    session.add(tpl)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Já existe template com esse nome") from exc
    session.refresh(tpl)
    return template_out(tpl)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: int, session: Session = Depends(get_session)) -> None:
    tpl = session.get(QueryTemplate, template_id)
    if tpl is None:
        raise HTTPException(404, "Template não encontrado")
    session.delete(tpl)
    session.commit()


@router.post("/history", response_model=HistoryOut, status_code=201)
async def add_history(dados: HistoryIn, session: Session = Depends(get_session)) -> HistoryOut:
    item = QueryHistory(query=dados.query, motor=dados.motor, origem=dados.origem)
    session.add(item)
    session.commit()
    session.refresh(item)
    retention.aplicar_politica(session)
    return HistoryOut.model_validate(item, from_attributes=True)


@router.get("/history", response_model=list[HistoryOut])
async def list_history(limit: int = 100, session: Session = Depends(get_session)) -> list[HistoryOut]:
    rows = session.exec(
        select(QueryHistory).order_by(col(QueryHistory.criado_em).desc(), col(QueryHistory.id).desc()).limit(min(limit, 1000))
    ).all()
    return [HistoryOut.model_validate(r, from_attributes=True) for r in rows]


@router.delete("/history")
async def clear_history(
    older_than_days: int | None = Query(default=None, ge=1),
    max_entries: int | None = Query(default=None, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    """Sem parâmetros apaga tudo; com older_than_days/max_entries faz poda seletiva."""
    if older_than_days is None and max_entries is None:
        total = len(session.exec(select(QueryHistory.id)).all())
        session.exec(delete(QueryHistory))  # type: ignore[call-overload]
        session.commit()
        return {"removidas": total}
    if max_entries == 0:
        max_entries = None
    return {"removidas": retention.podar_historico(session, older_than_days, max_entries)}
