from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app.config import get_settings
from app.db import get_engine, get_session
from app.models._base import agora
from app.models.invite import Invite
from app.services import convites as svc
from app.services import evidence_store, query_compose
from app.services.scraper import get_scraper
from app.services.searxng_client import SearxngIndisponivel, get_searxng

router = APIRouter(prefix="/api/invites", tags=["invites"])

# Dorks do PDF (deeplinks Google) — mantidos para compatibilidade
REDES_PDF = svc.REDES_PDF
PADROES = svc.PADROES_PDF
montar_queries = svc.montar_queries_pdf

PLATAFORMAS = ("whatsapp", "whatsapp_canal", "telegram", "telegram_publico")


class InviteOut(BaseModel):
    id: int
    plataforma: str
    url: str
    termo: str
    origem: str
    first_seen: datetime
    last_seen: datetime
    hash_conteudo: str
    # v2
    fonte_url: str = ""
    status: str = "desconhecido"
    nome_grupo: str | None = None
    membros: int | None = None
    descricao: str | None = None
    verificado_em: datetime | None = None
    evidencia_id: int | None = None
    score_relevancia: int = 0
    http_status: int = 0
    erro_verificacao: str = ""


class ScanIn(BaseModel):
    termo: str = Field(min_length=1, max_length=200)
    plataformas: list[Literal["whatsapp", "telegram"]] = ["whatsapp", "telegram"]
    engines: list[Literal["duckduckgo", "bing", "startpage"]] = ["duckduckgo", "bing", "startpage"]
    max_consultas: int = Field(default=3, ge=1, le=6)  # consultas SearXNG por plataforma (uma por dork)


class ScanFonte(BaseModel):
    plataforma: str
    fonte: str
    query: str = ""
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


class ExtrairIn(BaseModel):
    texto: str = Field(min_length=1, max_length=200_000)
    termo: str = Field(default="manual", max_length=200)
    fonte_url: str = Field(default="", max_length=2000)
    registrar: bool = False


class RegistrarIn(BaseModel):
    url: str = Field(min_length=10, max_length=500)
    termo: str = Field(default="manual", max_length=200)
    fonte_url: str = Field(default="", max_length=2000)


class TestarTodosIn(BaseModel):
    ids: list[int] = []
    ignorar_robots: bool = False
    apenas_nao_verificados: bool = False


def _out(inv: Invite) -> InviteOut:
    return InviteOut.model_validate(inv, from_attributes=True)


def _plataforma_base(p: str) -> str:
    return "whatsapp" if p.startswith("whatsapp") else "telegram"


@router.get("/queries")
async def queries(termo: str = Query(min_length=1, max_length=200)) -> dict:
    qs = svc.montar_queries_pdf(termo)
    return {
        "termo": termo,
        "queries": qs,
        "deeplinks": {plat: query_compose.deeplinks(q) for plat, q in qs.items()},
        "queries_searxng": svc.montar_queries_searxng(termo),
    }


def _upsert(session: Session, plat: str, url: str, termo: str, origem: str, fonte_url: str, hash_conteudo: str) -> tuple[Invite, bool]:
    inv = session.exec(select(Invite).where(Invite.url == url)).first()
    novo = inv is None
    if inv is None:
        inv = Invite(plataforma=plat, url=url, termo=termo, origem=origem, fonte_url=fonte_url, hash_conteudo=hash_conteudo)
    else:
        inv.last_seen = agora()
        inv.hash_conteudo = hash_conteudo or inv.hash_conteudo
        if fonte_url and not inv.fonte_url:
            inv.fonte_url = fonte_url
    session.add(inv)
    return inv, novo


@router.post("/scan", response_model=ScanOut)
async def scan(dados: ScanIn, session: Session = Depends(get_session)) -> ScanOut:
    """Consultas ao SearXNG local (dorks sem parênteses/OR, que Bing/DDG honram); convites extraídos de URL/título/snippet."""
    return await executar_scan(session, dados.termo, list(dados.plataformas), list(dados.engines), dados.max_consultas)


async def executar_scan(session: Session, termo: str, plataformas: list[str], engines: list[str], max_consultas: int = 3, origem: str = "searxng") -> ScanOut:
    """Núcleo do scan (também usado pelas Convocações: termos do cartaz → convites abertos)."""
    cliente = get_searxng()
    qs = svc.montar_queries_searxng(termo)
    fonte = "searxng:" + ",".join(engines)
    execucoes: list[ScanFonte] = []
    novos = atualizados = 0
    tocados: list[Invite] = []
    for plat in plataformas:
        for q in qs[plat][:max_consultas]:
            try:
                res = await cliente.buscar(q, engines)
            except SearxngIndisponivel as exc:
                raise HTTPException(503, str(exc)) from exc
            achados: list[tuple[str, str, str]] = []  # (plataforma, url, fonte_url)
            if res.ok:
                for r in res.resultados:
                    texto = " ".join(str(r.get(k, "")) for k in ("url", "titulo", "content"))
                    for p, u in svc.extrair_convites(texto):
                        if _plataforma_base(p) == plat:
                            achados.append((p, u, r.get("url", "")))
            vistos: set[str] = set()
            for p, u, fonte_url in achados:
                if u in vistos:
                    continue
                vistos.add(u)
                inv, novo = _upsert(session, p, u, termo, res.url, fonte_url, res.sha256)
                novos += int(novo)
                atualizados += int(not novo)
                tocados.append(inv)
            execucoes.append(
                ScanFonte(
                    plataforma=plat, fonte=fonte, query=q, resultados_busca=len(res.resultados), engines_sem_resposta=res.engines_sem_resposta,
                    url=res.url, status=res.status, erro=res.erro, sha256=res.sha256, coletado_em=res.coletado_em, encontrados=len(vistos),
                )
            )
    session.commit()
    saida: dict[str, InviteOut] = {}
    for inv in tocados:
        session.refresh(inv)
        saida[inv.url] = _out(inv)
    return ScanOut(termo=termo, novos=novos, atualizados=atualizados, execucoes=execucoes, convites=list(saida.values()))


@router.post("/extrair")
async def extrair(dados: ExtrairIn, session: Session = Depends(get_session)) -> dict:
    """Extrai convites de um texto colado (post, descrição, OCR). `registrar=true` grava na tabela."""
    achados = svc.extrair(dados.texto)
    registrados: list[InviteOut] = []
    if dados.registrar:
        for c in achados:
            inv, _ = _upsert(session, c.plataforma, c.url, dados.termo, "manual", dados.fonte_url, "")
            registrados.append(inv)  # type: ignore[arg-type]
        session.commit()
        registrados = [_out(session.exec(select(Invite).where(Invite.url == c.url)).one()) for c in achados]
    return {"convites": [{"plataforma": c.plataforma, "url": c.url, "codigo": c.codigo} for c in achados], "registrados": registrados}


@router.post("/registrar", response_model=InviteOut, status_code=201)
async def registrar(dados: RegistrarIn, session: Session = Depends(get_session)) -> Invite:
    achados = svc.extrair(dados.url)
    if not achados:
        raise HTTPException(422, "URL não é um convite reconhecido (chat.whatsapp.com, whatsapp.com/channel, t.me/+, t.me/joinchat, t.me/<canal>)")
    c = achados[0]
    inv, _ = _upsert(session, c.plataforma, c.url, dados.termo, "manual", dados.fonte_url, "")
    session.commit()
    session.refresh(inv)
    return inv


def _listar(session: Session, plataforma: str | None, termo: str | None, status: str | None = None) -> list[Invite]:
    stmt = select(Invite)
    if plataforma:
        stmt = stmt.where(col(Invite.plataforma).startswith(plataforma)) if plataforma in ("whatsapp", "telegram") else stmt.where(Invite.plataforma == plataforma)
    if termo:
        stmt = stmt.where(col(Invite.termo).contains(termo))
    if status:
        stmt = stmt.where(Invite.status == status)
    return list(session.exec(stmt.order_by(col(Invite.last_seen).desc())).all())


@router.get("", response_model=list[InviteOut])
async def listar(plataforma: str | None = None, termo: str | None = None, status: str | None = None, session: Session = Depends(get_session)) -> list[Invite]:
    return _listar(session, plataforma, termo, status)


@router.get("/export")
async def exportar(formato: Literal["csv", "json"] = "csv", session: Session = Depends(get_session)) -> Response:
    rows = [_out(i).model_dump(mode="json") for i in _listar(session, None, None)]
    if formato == "json":
        return Response(json.dumps(rows, ensure_ascii=False, indent=2), media_type="application/json", headers={"Content-Disposition": 'attachment; filename="convites.json"'})
    buf = io.StringIO()
    campos = list(InviteOut.model_fields)
    w = csv.DictWriter(buf, fieldnames=campos)
    w.writeheader()
    w.writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="convites.csv"'})


# ------------------------------------------------------------------ verificação
def _prefs():  # noqa: ANN202
    from app.routers.settings import carregar

    return carregar().preferencias


async def verificar_convite(session: Session, inv: Invite, ignorar_robots: bool = False) -> svc.VerificacaoConvite:
    """GET da página pública do convite; grava status/nome/membros e a foto do grupo como evidência."""
    scraper = get_scraper()
    respeitar = _prefs().convitesRespeitarRobots and not ignorar_robots
    v = await svc.verificar(scraper, inv, respeitar_robots=respeitar)
    inv.status = v.status
    inv.verificado_em = v.verificado_em
    inv.http_status = v.http_status
    inv.erro_verificacao = v.erro or ""
    if v.status == "ativo":
        inv.nome_grupo = v.nome_grupo
        inv.membros = v.membros
        inv.descricao = v.descricao
        inv.score_relevancia = svc.score_relevancia(v.nome_grupo, v.descricao, inv.termo if inv.termo not in ("manual", "convocacoes") else "")
        if v.foto_url and inv.evidencia_id is None:
            rb = await scraper.buscar_bytes(v.foto_url, respeitar_robots=respeitar)
            if rb.ok and rb.mime.startswith("image/"):
                try:
                    ev = evidence_store.salvar_bytes(rb.conteudo, f"grupo_{inv.id or 'novo'}.{rb.mime.split('/')[-1].replace('jpeg', 'jpg')}", rb.mime, origem_url=inv.url, tipo="imagem", notas=f"Foto do grupo/canal: {v.nome_grupo or inv.url}", limite_bytes=get_settings().max_download_mb * 1024 * 1024)
                    session.add(ev)
                    session.commit()
                    session.refresh(ev)
                    evidence_store.registrar_manifesto(ev)
                    inv.evidencia_id = ev.id
                except ValueError:
                    pass
    session.add(inv)
    session.commit()
    session.refresh(inv)
    return v


@router.post("/{invite_id}/testar")
async def testar(invite_id: int, ignorar_robots: bool = False, session: Session = Depends(get_session)) -> dict:
    inv = session.get(Invite, invite_id)
    if inv is None:
        raise HTTPException(404, "Convite não encontrado")
    v = await verificar_convite(session, inv, ignorar_robots)
    return {"convite": _out(inv).model_dump(mode="json"), "verificacao": v.como_dict()}


async def verificar_lote(session: Session, ids: list[int] | None = None, limite: int = 20, ignorar_robots: bool = False, apenas_nao_verificados: bool = False) -> dict[str, int]:
    stmt = select(Invite)
    if ids:
        stmt = stmt.where(col(Invite.id).in_(ids))
    if apenas_nao_verificados:
        stmt = stmt.where(Invite.verificado_em == None)  # noqa: E711
    stmt = stmt.order_by(col(Invite.verificado_em).asc().nulls_first(), col(Invite.last_seen).desc()).limit(limite)
    stats = {"verificados": 0, "ativos": 0, "revogados": 0, "desconhecidos": 0}
    for inv in session.exec(stmt).all():
        v = await verificar_convite(session, inv, ignorar_robots)
        stats["verificados"] += 1
        stats[{"ativo": "ativos", "revogado": "revogados"}.get(v.status, "desconhecidos")] += 1
    return stats


async def _lote_em_background(ids: list[int], ignorar_robots: bool, apenas_nao_verificados: bool) -> None:
    from sqlmodel import Session as _S

    with _S(get_engine()) as s:
        await verificar_lote(s, ids or None, limite=len(ids) if ids else 50, ignorar_robots=ignorar_robots, apenas_nao_verificados=apenas_nao_verificados)


@router.post("/testar-todos")
async def testar_todos(dados: TestarTodosIn, tarefas: BackgroundTasks, session: Session = Depends(get_session)) -> dict:
    """Verifica em sequência (rate limit do scraper já impõe 3 s/domínio). Roda em background; acompanhe pela listagem."""
    stmt = select(Invite.id)
    if dados.ids:
        stmt = stmt.where(col(Invite.id).in_(dados.ids))
    if dados.apenas_nao_verificados:
        stmt = stmt.where(Invite.verificado_em == None)  # noqa: E711
    ids = list(session.exec(stmt).all())
    if not ids:
        return {"agendados": 0}
    tarefas.add_task(_lote_em_background, ids, dados.ignorar_robots, dados.apenas_nao_verificados)
    return {"agendados": len(ids)}


@router.delete("/{invite_id}", status_code=204)
async def remover(invite_id: int, session: Session = Depends(get_session)) -> None:
    inv = session.get(Invite, invite_id)
    if inv is None:
        raise HTTPException(404, "Convite não encontrado")
    session.delete(inv)
    session.commit()
