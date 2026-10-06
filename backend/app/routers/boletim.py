from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlmodel import Session, col, select

from app.db import get_session
from app.models.boletim import BoletimItem, Perfil
from app.models.evidence import Evidence
from app.models.hashtag import Hashtag
from app.models.invite import Invite
from app.routers.agenda import _listar as listar_agenda
from app.routers.agenda import evento_out
from app.schemas.boletim import BoletimItemIn, BoletimItemOut, BoletimItemPatch, BoletimOut, PerfilOut
from app.services import boletim as svc
from app.services.agenda import dia_semana

router = APIRouter(prefix="/api/boletim", tags=["boletim"])


def _get_item(session: Session, item_id: int) -> BoletimItem:
    item = session.get(BoletimItem, item_id)
    if item is None:
        raise HTTPException(404, "Item não encontrado")
    return item


def _checar_evidencia(session: Session, evidence_id: int | None) -> None:
    if evidence_id is not None and session.get(Evidence, evidence_id) is None:
        raise HTTPException(422, f"evidência #{evidence_id} não encontrada")


@router.get("/itens", response_model=list[BoletimItemOut])
async def listar_itens(data: date | None = None, secao: str | None = None, session: Session = Depends(get_session)) -> list[BoletimItem]:
    stmt = select(BoletimItem)
    if data:
        stmt = stmt.where(BoletimItem.data == data)
    if secao:
        stmt = stmt.where(BoletimItem.secao == secao)
    return list(session.exec(stmt.order_by(col(BoletimItem.data).desc(), BoletimItem.secao, BoletimItem.id)).all())


@router.post("/itens", response_model=BoletimItemOut, status_code=201)
async def criar_item(dados: BoletimItemIn, session: Session = Depends(get_session)) -> BoletimItem:
    _checar_evidencia(session, dados.evidence_id)
    item = BoletimItem(**dados.model_dump())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.patch("/itens/{item_id}", response_model=BoletimItemOut)
async def atualizar_item(item_id: int, dados: BoletimItemPatch, session: Session = Depends(get_session)) -> BoletimItem:
    item = _get_item(session, item_id)
    campos = dados.model_dump(exclude_unset=True)
    if "evidence_id" in campos:
        _checar_evidencia(session, campos["evidence_id"])
    for k, v in campos.items():
        setattr(item, k, v)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/itens/{item_id}", status_code=204)
async def remover_item(item_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_get_item(session, item_id))
    session.commit()


def _contexto(session: Session, data: date) -> dict:
    itens = session.exec(select(BoletimItem).where(BoletimItem.data == data).order_by(BoletimItem.id)).all()
    secoes: dict[str, list[BoletimItem]] = {}
    for i in itens:
        secoes.setdefault(i.secao, []).append(i)
    agenda = listar_agenda(session, data=data)
    perfis = session.exec(select(Perfil).where(Perfil.ativo == True).order_by(Perfil.categoria, Perfil.rotulo, Perfil.handle)).all()  # noqa: E712
    hashtags = session.exec(select(Hashtag).where(Hashtag.contagem > 0).order_by(col(Hashtag.contagem).desc(), Hashtag.tag).limit(15)).all()
    limite = data - timedelta(days=7)
    convites = [
        {"plataforma": c.plataforma, "url": c.url, "termo": c.termo, "last_seen": c.last_seen.date().isoformat()}
        for c in session.exec(select(Invite).order_by(col(Invite.last_seen).desc()).limit(50)).all()
        if c.last_seen.date() >= limite and c.last_seen.date() <= data
    ][:20]
    return {
        "data": data,
        "secoes": secoes,
        "agenda": agenda,
        "perfis": list(perfis),
        "hashtags": [h.tag for h in hashtags],
        "hashtags_detalhe": [{"tag": h.tag, "contagem": h.contagem, "fonte": h.fonte} for h in hashtags],
        "convites": convites,
    }


@router.get("/{data}", response_model=BoletimOut)
async def boletim(data: date, session: Session = Depends(get_session)) -> BoletimOut:
    """Boletim consolidado do dia: itens curados + agenda + perfis ativos + hashtags + convites recentes."""
    ctx = _contexto(session, data)
    eventos = [evento_out(e) for e in ctx["agenda"]]
    por_cand: dict[str, list] = {}
    for e in eventos:
        por_cand.setdefault(e.candidato, []).append(e.model_dump(mode="json"))
    return BoletimOut(
        data=data,
        titulo=svc.titulo_boletim(data),
        dia_semana=dia_semana(data),
        secoes={s: [BoletimItemOut.model_validate(i, from_attributes=True) for i in itens] for s, itens in ctx["secoes"].items()},
        agenda={"total": len(eventos), "com_impacto_rodovia": sum(1 for e in eventos if e.impacto_rodovia), "por_candidato": por_cand},
        perfis=[PerfilOut.model_validate(p, from_attributes=True) for p in ctx["perfis"]],
        hashtags=ctx["hashtags_detalhe"],
        convites=ctx["convites"],
        markdown=svc.gerar_markdown(ctx),
    )


@router.get("/{data}/export")
async def exportar(data: date, formato: Literal["md", "json", "html"] = "md", session: Session = Depends(get_session)) -> Response:
    ctx = _contexto(session, data)
    nome = f"boletim_{data.isoformat()}"
    if formato == "html":
        return HTMLResponse(svc.gerar_html(ctx))
    if formato == "json":
        corpo = {
            "data": data.isoformat(),
            "titulo": svc.titulo_boletim(data),
            "secoes": {s: [BoletimItemOut.model_validate(i, from_attributes=True).model_dump(mode="json") for i in itens] for s, itens in ctx["secoes"].items()},
            "agenda": [evento_out(e).model_dump(mode="json") for e in ctx["agenda"]],
            "perfis": [PerfilOut.model_validate(p, from_attributes=True).model_dump(mode="json") for p in ctx["perfis"]],
            "hashtags": ctx["hashtags_detalhe"],
            "convites": ctx["convites"],
        }
        return Response(json.dumps(corpo, ensure_ascii=False, indent=2), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{nome}.json"'})
    return Response(svc.gerar_markdown(ctx), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{nome}.md"'})
