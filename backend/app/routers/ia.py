"""Assistente de IA: status, fila de tarefas, aprovações (Boletim/Agenda), custo e ação local para o agent do Telegram."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.db import get_session
from app.middleware_auth import acesso_local_direto
from app.models.auth import Usuario
from app.models.ia import IaTarefa
from app.routers.auth import usuario_atual
from app.services import scheduler
from app.services.ia import pipeline
from app.services.ia.cliente_openclaw import OpenClawErro, OpenClawIndisponivel, RespostaInvalida, get_cliente

router = APIRouter(prefix="/api/ia", tags=["ia"])


# ------------------------------------------------------------------ schemas
class TarefaOut(BaseModel):
    id: int
    origem: str
    hit_id: int | None
    deteccao_id: int | None
    monitor_id: int | None
    monitor_nome: str
    url: str
    titulo: str
    resumo: str
    fonte_nome: str
    termos: str
    publicado_em: datetime | None
    texto_chars: int
    status: str
    etapa: str
    tentativas: int
    erro: str
    veredito: str | None
    severidade: str | None
    justificativa: str
    secao_sugerida: str | None
    eh_evento: bool
    triagem: dict[str, Any]
    evento: dict[str, Any]
    pesquisa: dict[str, Any]
    cartao: dict[str, Any]
    aterramento: dict[str, Any] = {}  # aditivo (2026-10-10)
    verificacao: dict[str, Any] = {}  # aditivo (2026-10-10): etiqueta de confiança OOVS
    aprovacao: str
    aprovado_por: str
    aprovado_em: datetime | None
    alerta_id: int | None
    boletim_item_id: int | None
    agenda_evento_id: int | None
    telegram_enviado: bool
    resumo_enviado: bool
    tokens_entrada: int
    tokens_saida: int
    custo_usd: float
    modelos: str
    criado_em: datetime
    iniciado_em: datetime | None
    concluido_em: datetime | None


class NovaTarefaIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    titulo: str = Field(default="", max_length=300)
    resumo: str = Field(default="", max_length=3000)


class AprovarIn(BaseModel):
    destino: Literal["boletim", "agenda", "ambos"] = "ambos"
    secao: str | None = None
    data: date | None = None
    titulo: str | None = Field(default=None, max_length=200)
    candidato: str | None = Field(default=None, max_length=120)
    por: str | None = Field(default=None, max_length=120)  # ex.: "telegram:371824016" quando o analista aprova pelo chat


class RejeitarIn(BaseModel):
    motivo: str = Field(default="", max_length=300)
    por: str | None = Field(default=None, max_length=120)


class ReprocessarIn(BaseModel):
    desde: Literal["triagem", "extracao", "pesquisa", "cartao"] = "triagem"


class CicloIn(BaseModel):
    limite: int | None = Field(default=None, ge=1, le=500)


def _out(t: IaTarefa) -> TarefaOut:
    def j(v: str) -> dict[str, Any]:
        try:
            d = json.loads(v or "{}")
        except ValueError:
            return {}
        return d if isinstance(d, dict) else {}

    return TarefaOut(**{**t.model_dump(exclude={"triagem_json", "evento_json", "pesquisa_json", "cartao_json", "aterramento_json", "verificacao_json"}), "triagem": j(t.triagem_json), "evento": j(t.evento_json), "pesquisa": j(t.pesquisa_json), "cartao": j(t.cartao_json), "aterramento": j(t.aterramento_json), "verificacao": j(t.verificacao_json)})


def _get(session: Session, tarefa_id: int) -> IaTarefa:
    t = session.get(IaTarefa, tarefa_id)
    if t is None:
        raise HTTPException(404, "tarefa não encontrada")
    return t


def _quem(usuario: Usuario, por: str | None) -> str:
    return (por or usuario.email or "painel")[:120]


def _erro(exc: pipeline.ErroPipeline) -> HTTPException:
    return HTTPException(exc.status, exc.detalhe)


# ------------------------------------------------------------------ status / fila
@router.get("/status")
async def status(session: Session = Depends(get_session)) -> dict[str, Any]:
    info = pipeline.status(session)
    job, job_r = scheduler.job_ia(), scheduler.job_ia_resumo()
    info["agendado"] = job is not None
    info["proximo_ciclo"] = job.next_run_time.isoformat() if job is not None and job.next_run_time else None
    info["proximo_resumo"] = job_r.next_run_time.isoformat() if job_r is not None and job_r.next_run_time else None
    return info


@router.get("/saude")
async def saude() -> dict[str, Any]:
    """Alcança o gateway do OpenClaw? (sem gastar tokens)"""
    c = get_cliente()
    return {"configurado": c.configurado, "url": c.base_url, "alcancavel": await c.disponivel()}


@router.get("/tarefas", response_model=list[TarefaOut])
async def listar(
    status: str | None = None,
    aprovacao: str | None = None,
    veredito: str | None = None,
    origem: str | None = None,
    monitor_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> list[TarefaOut]:
    stmt = select(IaTarefa)
    if status:
        stmt = stmt.where(IaTarefa.status == status)
    if aprovacao:
        stmt = stmt.where(IaTarefa.aprovacao == aprovacao)
    if veredito:
        stmt = stmt.where(IaTarefa.veredito == veredito.upper())
    if origem:
        stmt = stmt.where(IaTarefa.origem == origem)
    if monitor_id is not None:
        stmt = stmt.where(IaTarefa.monitor_id == monitor_id)
    return [_out(t) for t in session.exec(stmt.order_by(col(IaTarefa.id).desc()).limit(limit)).all()]


@router.get("/tarefas/{tarefa_id}", response_model=TarefaOut)
async def obter(tarefa_id: int, session: Session = Depends(get_session)) -> TarefaOut:
    return _out(_get(session, tarefa_id))


@router.post("/tarefas", response_model=TarefaOut, status_code=201)
async def criar(dados: NovaTarefaIn, usuario: Usuario = Depends(usuario_atual), session: Session = Depends(get_session)) -> TarefaOut:
    """Enfileira manualmente uma URL (teste ou pedido do analista)."""
    if not dados.url.startswith(("http://", "https://")):
        raise HTTPException(422, "url deve começar com http:// ou https://")
    try:
        return _out(pipeline.enfileirar_manual(session, dados.url, dados.titulo, dados.resumo, por=usuario.email))
    except pipeline.ErroPipeline as exc:
        raise _erro(exc) from exc


@router.post("/ciclo")
async def ciclo(dados: CicloIn | None = None, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Processa a fila agora (respeita o teto diário e o limite por ciclo)."""
    return await pipeline.processar_fila(session, limite=dados.limite if dados else None)


@router.post("/resumo")
async def resumo(session: Session = Depends(get_session)) -> dict[str, Any]:
    return await pipeline.enviar_resumo(session, forcar=True)


@router.get("/custo")
async def custo(dias: int = Query(default=7, ge=1, le=90), session: Session = Depends(get_session)) -> dict[str, Any]:
    serie = pipeline.custo_por_dia(session, dias)
    return {"dias": serie, "total_usd": round(sum(d["custo_usd"] for d in serie), 4), "total_chamadas": sum(d["chamadas"] for d in serie)}


# ------------------------------------------------------------------ aprovação / ações
@router.post("/tarefas/{tarefa_id}/aprovar")
async def aprovar(tarefa_id: int, dados: AprovarIn, usuario: Usuario = Depends(usuario_atual), session: Session = Depends(get_session)) -> dict[str, Any]:
    t = _get(session, tarefa_id)
    ajustes = {k: v for k, v in dados.model_dump().items() if k in ("secao", "data", "titulo", "candidato") and v is not None}
    try:
        return pipeline.aprovar(session, t, destino=dados.destino, por=_quem(usuario, dados.por), ajustes=ajustes)
    except pipeline.ErroPipeline as exc:
        raise _erro(exc) from exc


@router.post("/tarefas/{tarefa_id}/rejeitar", response_model=TarefaOut)
async def rejeitar(tarefa_id: int, dados: RejeitarIn, usuario: Usuario = Depends(usuario_atual), session: Session = Depends(get_session)) -> TarefaOut:
    return _out(pipeline.rejeitar(session, _get(session, tarefa_id), por=_quem(usuario, dados.por), motivo=dados.motivo))


@router.post("/tarefas/{tarefa_id}/reprocessar", response_model=TarefaOut)
async def reprocessar(tarefa_id: int, dados: ReprocessarIn, session: Session = Depends(get_session)) -> TarefaOut:
    try:
        t = pipeline.reprocessar(session, _get(session, tarefa_id), dados.desde)
    except pipeline.ErroPipeline as exc:
        raise _erro(exc) from exc
    scheduler.acordar_ia()
    return _out(t)


@router.post("/tarefas/{tarefa_id}/pesquisar")
async def pesquisar(tarefa_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Aprofunda sob pedido (agent pesquisador + novo cartão)."""
    try:
        return await pipeline.pesquisar_sob_pedido(session, _get(session, tarefa_id))
    except pipeline.ErroPipeline as exc:
        raise _erro(exc) from exc
    except OpenClawIndisponivel as exc:
        raise HTTPException(503, str(exc)) from exc
    except (OpenClawErro, RespostaInvalida) as exc:
        raise HTTPException(502, str(exc)) from exc


@router.delete("/tarefas/{tarefa_id}", status_code=204)
async def remover(tarefa_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_get(session, tarefa_id))
    session.commit()


@router.get("/tarefas/{tarefa_id}/acao")
async def acao_local(
    tarefa_id: int,
    request: Request,
    acao: Literal["aprovar", "rejeitar", "pesquisar"],
    destino: Literal["boletim", "agenda", "ambos"] = "ambos",
    por: str = Query(default="telegram", max_length=120),
    motivo: str = Query(default="", max_length=300),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Ação por GET, SÓ para processos locais (o agent `analista` do OpenClaw, que só consegue fazer GET pelo web_fetch).

    Requisições vindas pelo Caddy trazem X-Forwarded-For e são recusadas: um link malicioso aberto no navegador do
    analista nunca aprova nada.
    """
    if not acesso_local_direto(request.scope):
        raise HTTPException(405, "ação por GET só é aceita de processos locais; use POST")
    t = _get(session, tarefa_id)
    try:
        if acao == "aprovar":
            return pipeline.aprovar(session, t, destino=destino, por=por)
        if acao == "rejeitar":
            return _out(pipeline.rejeitar(session, t, por=por, motivo=motivo)).model_dump(mode="json")
        return await pipeline.pesquisar_sob_pedido(session, t)
    except pipeline.ErroPipeline as exc:
        raise _erro(exc) from exc
    except OpenClawIndisponivel as exc:
        raise HTTPException(503, str(exc)) from exc
    except (OpenClawErro, RespostaInvalida) as exc:
        raise HTTPException(502, str(exc)) from exc
