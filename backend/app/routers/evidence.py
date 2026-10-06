from __future__ import annotations

import mimetypes
import re
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.config import get_settings
from app.db import get_session
from app.models.evidence import Evidence
from app.services import evidence_store

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


class EvidenceOut(BaseModel):
    id: int
    tipo: str
    origem_url: str | None
    arquivo: str
    nome_original: str
    tamanho: int
    mime: str
    sha256: str
    criado_em: datetime
    notas: str


class ExportIn(BaseModel):
    ids: list[int] = []


def criar_evidencia(
    session: Session, upload: UploadFile, tipo: str, origem_url: str | None, notas: str
) -> Evidence:
    limite = get_settings().max_upload_mb * 1024 * 1024
    try:
        rel, sha, tamanho = evidence_store.salvar(upload.file, upload.filename or "arquivo", limite)
    except ValueError as exc:
        raise HTTPException(413, str(exc)) from exc
    mime = upload.content_type or mimetypes.guess_type(upload.filename or "")[0] or "application/octet-stream"
    if tipo == "auto":
        tipo = "imagem" if mime.startswith("image/") else "arquivo"
    ev = Evidence(
        tipo=tipo,
        origem_url=origem_url or None,
        arquivo=rel,
        nome_original=upload.filename or "",
        tamanho=tamanho,
        mime=mime,
        sha256=sha,
        notas=notas,
    )
    session.add(ev)
    session.commit()
    session.refresh(ev)
    evidence_store.registrar_manifesto(ev)
    return ev


def _get(session: Session, evidence_id: int) -> Evidence:
    ev = session.get(Evidence, evidence_id)
    if ev is None:
        raise HTTPException(404, "Evidência não encontrada")
    return ev


@router.post("", response_model=EvidenceOut, status_code=201)
async def upload(
    arquivo: UploadFile = File(...),
    tipo: str = Form("auto"),
    origem_url: str | None = Form(None),
    notas: str = Form(""),
    session: Session = Depends(get_session),
) -> Evidence:
    return criar_evidencia(session, arquivo, tipo, origem_url, notas)


@router.get("", response_model=list[EvidenceOut])
async def listar(tipo: str | None = None, session: Session = Depends(get_session)) -> list[Evidence]:
    stmt = select(Evidence)
    if tipo:
        stmt = stmt.where(Evidence.tipo == tipo)
    return list(session.exec(stmt.order_by(col(Evidence.criado_em).desc(), col(Evidence.id).desc())).all())


class ByHashOut(BaseModel):
    sha256: str
    total: int
    primeira_coleta: EvidenceOut
    ocorrencias: list[EvidenceOut]


@router.get("/by-hash/{sha256}", response_model=ByHashOut)
async def por_hash(sha256: str, session: Session = Depends(get_session)) -> ByHashOut:
    """Dedup + prova de primeira coleta: todas as evidências com o mesmo SHA-256, da mais antiga à mais nova."""
    sha = sha256.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise HTTPException(422, "SHA-256 deve ter 64 caracteres hexadecimais")
    rows = session.exec(select(Evidence).where(Evidence.sha256 == sha).order_by(Evidence.criado_em, Evidence.id)).all()
    if not rows:
        raise HTTPException(404, "Nenhuma evidência com esse hash")
    itens = [EvidenceOut.model_validate(r, from_attributes=True) for r in rows]
    return ByHashOut(sha256=sha, total=len(itens), primeira_coleta=itens[0], ocorrencias=itens)


@router.get("/{evidence_id}", response_model=EvidenceOut)
async def obter(evidence_id: int, session: Session = Depends(get_session)) -> Evidence:
    return _get(session, evidence_id)


@router.get("/{evidence_id}/download")
async def download(evidence_id: int, inline: bool = False, session: Session = Depends(get_session)) -> FileResponse:
    ev = _get(session, evidence_id)
    p = evidence_store.caminho_absoluto(ev)
    if not p.exists():
        raise HTTPException(410, "Arquivo ausente no disco")
    return FileResponse(
        p,
        media_type=ev.mime,
        filename=ev.nome_original or p.name,
        content_disposition_type="inline" if inline else "attachment",
        headers={"X-Content-SHA256": ev.sha256},
    )


@router.get("/{evidence_id}/verify")
async def verificar(evidence_id: int, session: Session = Depends(get_session)) -> dict:
    return evidence_store.verificar(_get(session, evidence_id))


class NotasIn(BaseModel):
    notas: str


@router.patch("/{evidence_id}", response_model=EvidenceOut)
async def atualizar_notas(evidence_id: int, dados: NotasIn, session: Session = Depends(get_session)) -> Evidence:
    ev = _get(session, evidence_id)
    ev.notas = dados.notas
    session.add(ev)
    session.commit()
    session.refresh(ev)
    evidence_store.registrar_manifesto(ev, "notas_atualizadas")
    return ev


@router.delete("/{evidence_id}", status_code=204)
async def remover(evidence_id: int, session: Session = Depends(get_session)) -> None:
    ev = _get(session, evidence_id)
    evidence_store.registrar_manifesto(ev, "removido")
    evidence_store.caminho_absoluto(ev).unlink(missing_ok=True)
    session.delete(ev)
    session.commit()


@router.post("/export")
async def exportar(dados: ExportIn, session: Session = Depends(get_session)) -> Response:
    stmt = select(Evidence).order_by(Evidence.id)
    if dados.ids:
        stmt = stmt.where(col(Evidence.id).in_(dados.ids))
    conteudo = evidence_store.exportar_zip(list(session.exec(stmt).all()))
    nome = f"evidencias_{datetime.now():%Y%m%d_%H%M%S}.zip"
    return Response(conteudo, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{nome}"'})
