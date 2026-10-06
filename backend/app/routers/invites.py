from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.db import get_session
from app.models._base import agora
from app.models.invite import Invite
from app.services import query_compose
from app.services.scraper import extrair_convites
from app.services.searxng_client import SearxngIndisponivel, get_searxng

router = APIRouter(prefix="/api/invites", tags=["invites"])

REDES_PDF = "(site:facebook.com OR site:instagram.com OR site:x.com OR site:tiktok.com)"
PADROES = {
    "whatsapp": REDES_PDF + ' (chat.whatsapp.com "{termo}")',
    "telegram": REDES_PDF + ' (t.me/joinchat "{termo}")',
}


def montar_queries(termo: str) -> dict[str, str]:
    t = " ".join(termo.replace('"', " ").split())
    return {plat: padrao.format(termo=t) for plat, padrao in PADROES.items()}


class InviteOut(BaseModel):
    id: int
    plataforma: str
    url: str
    termo: str
    origem: str
    first_seen: datetime
    last_seen: datetime
    hash_conteudo: str


class ScanIn(BaseModel):
    termo: str = Field(min_length=1, max_length=200)
    plataformas: list[Literal["whatsapp", "telegram"]] = ["whatsapp", "telegram"]
    engines: list[Literal["duckduckgo", "bing", "startpage"]] = ["duckduckgo", "bing", "startpage"]


class ScanFonte(BaseModel):
    plataforma: str
    fonte: str
    resultados_busca: int = 0
    engines_sem_resposta: list[Any] = []
    url: str
    status: int
    erro: str | None
    sha256: str
    coletado_em: str
    encontrados: int


class ScanOut(BaseModel):
    termo: str
    novos: int
    atualizados: int
    execucoes: list[ScanFonte]
    convites: list[InviteOut]


@router.get("/queries")
async def queries(termo: str = Query(min_length=1, max_length=200)) -> dict:
    qs = montar_queries(termo)
    return {
        "termo": termo,
        "queries": qs,
        "deeplinks": {plat: query_compose.deeplinks(q) for plat, q in qs.items()},
    }


@router.post("/scan", response_model=ScanOut)
async def scan(dados: ScanIn, session: Session = Depends(get_session)) -> ScanOut:
    """Uma consulta ao SearXNG local por plataforma; convites extraídos de URL/título/snippet."""
    cliente = get_searxng()
    qs = montar_queries(dados.termo)
    fonte = "searxng:" + ",".join(dados.engines)
    execucoes: list[ScanFonte] = []
    novos = atualizados = 0
    tocados: list[Invite] = []
    for plat in dados.plataformas:
        try:
            res = await cliente.buscar(qs[plat], dados.engines)
        except SearxngIndisponivel as exc:
            raise HTTPException(503, str(exc)) from exc
        achados = [(p, u) for p, u in extrair_convites(res.texto_concatenado()) if p == plat] if res.ok else []
        for p, u in achados:
            inv = session.exec(select(Invite).where(Invite.url == u)).first()
            if inv is None:
                inv = Invite(plataforma=p, url=u, termo=dados.termo, origem=res.url, hash_conteudo=res.sha256)
                novos += 1
            else:
                inv.last_seen = agora()
                inv.hash_conteudo = res.sha256
                atualizados += 1
            session.add(inv)
            tocados.append(inv)
        execucoes.append(
            ScanFonte(
                plataforma=plat,
                fonte=fonte,
                resultados_busca=len(res.resultados),
                engines_sem_resposta=res.engines_sem_resposta,
                url=res.url,
                status=res.status,
                erro=res.erro,
                sha256=res.sha256,
                coletado_em=res.coletado_em,
                encontrados=len(achados),
            )
        )
    session.commit()
    vistos: dict[str, InviteOut] = {}
    for inv in tocados:
        session.refresh(inv)
        vistos[inv.url] = InviteOut.model_validate(inv, from_attributes=True)
    return ScanOut(termo=dados.termo, novos=novos, atualizados=atualizados, execucoes=execucoes, convites=list(vistos.values()))


def _listar(session: Session, plataforma: str | None, termo: str | None) -> list[Invite]:
    stmt = select(Invite)
    if plataforma:
        stmt = stmt.where(Invite.plataforma == plataforma)
    if termo:
        stmt = stmt.where(col(Invite.termo).contains(termo))
    return list(session.exec(stmt.order_by(col(Invite.last_seen).desc())).all())


@router.get("", response_model=list[InviteOut])
async def listar(plataforma: str | None = None, termo: str | None = None, session: Session = Depends(get_session)) -> list[Invite]:
    return _listar(session, plataforma, termo)


@router.get("/export")
async def exportar(formato: Literal["csv", "json"] = "csv", session: Session = Depends(get_session)) -> Response:
    rows = [InviteOut.model_validate(i, from_attributes=True).model_dump(mode="json") for i in _listar(session, None, None)]
    if formato == "json":
        return Response(
            json.dumps(rows, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="convites.json"'},
        )
    buf = io.StringIO()
    campos = list(InviteOut.model_fields)
    w = csv.DictWriter(buf, fieldnames=campos)
    w.writeheader()
    w.writerows(rows)
    return Response(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="convites.csv"'},
    )


@router.delete("/{invite_id}", status_code=204)
async def remover(invite_id: int, session: Session = Depends(get_session)) -> None:
    inv = session.get(Invite, invite_id)
    if inv is None:
        raise HTTPException(404, "Convite não encontrado")
    session.delete(inv)
    session.commit()
