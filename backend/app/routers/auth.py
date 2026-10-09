"""Rotas de autenticação (/api/auth) e administração de usuários (só papel admin)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.middleware_auth import COOKIE, acesso_local_direto, csrf_ok, ip_do_cliente
from app.models.auth import EventoAcesso, Sessao, Usuario
from app.services import auth as svc

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ------------------------------------------------------------------ schemas
class SolicitarIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class VerificarIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    codigo: str = Field(min_length=6, max_length=7)


class UsuarioOut(BaseModel):
    id: int
    email: str
    nome: str
    papel: str
    ativo: bool
    telegram_chat_id: str | None
    criado_em: datetime
    criado_por: str
    ultimo_login: datetime | None


class UsuarioIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    nome: str = ""
    papel: str = "analista"
    telegram_chat_id: str | None = None


class UsuarioPatch(BaseModel):
    nome: str | None = None
    papel: str | None = None
    ativo: bool | None = None
    telegram_chat_id: str | None = None


class SessaoOut(BaseModel):
    id: int
    criado_em: datetime
    ultimo_uso: datetime
    expira_em: datetime
    ip: str
    user_agent: str
    atual: bool


class EventoOut(BaseModel):
    id: int
    em: datetime
    evento: str
    email: str
    ip: str
    ok: bool
    detalhe: str


# ------------------------------------------------------------------ dependências
_LOCAL = Usuario(id=0, email="local", nome="Acesso local", papel="admin", ativo=True)


def usuario_atual(request: Request, session: Session = Depends(get_session)) -> Usuario:
    if not get_settings().auth_enabled or acesso_local_direto(request.scope):
        return _LOCAL
    u = getattr(request.state, "usuario", None)
    if u is None:  # rotas /api/auth/* não passam pelo porteiro: valida aqui
        par = svc.obter_sessao(session, request.cookies.get(COOKIE))
        if par is None:
            raise HTTPException(401, "não autenticado", headers={"Cache-Control": "no-store"})
        u = par[1]
    return u


def exigir_admin(request: Request, usuario: Usuario = Depends(usuario_atual)) -> Usuario:
    if usuario.papel != "admin":
        raise HTTPException(403, "apenas administradores")
    if get_settings().auth_enabled and request.method not in ("GET", "HEAD") and usuario is not _LOCAL and not csrf_ok(request):
        raise HTTPException(403, "requisição recusada (CSRF)")
    return usuario


def _cookie(response: Response, token: str | None) -> None:
    s = get_settings()
    if token is None:
        response.delete_cookie(COOKIE, path="/", secure=s.auth_cookie_secure, httponly=True, samesite="strict")
        return
    response.set_cookie(COOKIE, token, max_age=s.auth_sessao_horas * 3600, path="/", secure=s.auth_cookie_secure, httponly=True, samesite="strict")


def _out(u: Usuario) -> UsuarioOut:
    return UsuarioOut.model_validate(u, from_attributes=True)


# ------------------------------------------------------------------ fluxo de login
@router.get("/estado")
async def estado(request: Request, session: Session = Depends(get_session)) -> dict:
    s = get_settings()
    info: dict = {"ativo": s.auth_enabled, "autenticado": False, "usuario": None, "canal": svc.canal_de_entrega(None), "validade_min": s.auth_codigo_minutos}
    if not s.auth_enabled or acesso_local_direto(request.scope):
        info.update(autenticado=True, usuario=_out(_LOCAL).model_dump(mode="json"))
        return info
    par = svc.obter_sessao(session, request.cookies.get(COOKIE))
    if par is not None:
        info.update(autenticado=True, usuario=_out(par[1]).model_dump(mode="json"))
    return info


@router.post("/solicitar")
async def solicitar(dados: SolicitarIn, request: Request, response: Response, session: Session = Depends(get_session)) -> dict:
    if not get_settings().auth_enabled:
        raise HTTPException(404, "autenticação desativada (defina O51NT_ADMIN_EMAIL)")
    response.headers["Cache-Control"] = "no-store"
    try:
        return await svc.solicitar_codigo(session, dados.email, ip_do_cliente(request))
    except svc.AuthErro as exc:
        raise HTTPException(exc.status, exc.detalhe) from exc


@router.post("/verificar")
async def verificar(dados: VerificarIn, request: Request, response: Response, session: Session = Depends(get_session)) -> dict:
    if not get_settings().auth_enabled:
        raise HTTPException(404, "autenticação desativada")
    response.headers["Cache-Control"] = "no-store"
    try:
        u, token = svc.verificar_codigo(session, dados.email, dados.codigo, ip_do_cliente(request), request.headers.get("user-agent", ""))
    except svc.AuthErro as exc:
        raise HTTPException(exc.status, exc.detalhe) from exc
    _cookie(response, token)
    return {"ok": True, "usuario": _out(u).model_dump(mode="json")}


@router.post("/sair")
async def sair(request: Request, response: Response, session: Session = Depends(get_session)) -> dict:
    token = request.cookies.get(COOKIE)
    par = svc.obter_sessao(session, token)
    svc.revogar_sessao(session, token)
    if par is not None:
        svc.registrar(session, "logout", email=par[1].email, ip=ip_do_cliente(request))
    _cookie(response, None)
    return {"ok": True}


@router.get("/eu", response_model=UsuarioOut)
async def eu(usuario: Usuario = Depends(usuario_atual)) -> UsuarioOut:
    return _out(usuario)


@router.get("/sessoes", response_model=list[SessaoOut])
async def sessoes(request: Request, usuario: Usuario = Depends(usuario_atual), session: Session = Depends(get_session)) -> list[SessaoOut]:
    atual_hash = svc.hash_segredo(request.cookies.get(COOKIE) or "")
    rows = session.exec(select(Sessao).where(Sessao.usuario_id == usuario.id, Sessao.revogada == False).order_by(Sessao.ultimo_uso.desc())).all()  # type: ignore[attr-defined]  # noqa: E712
    return [SessaoOut(id=r.id, criado_em=r.criado_em, ultimo_uso=r.ultimo_uso, expira_em=r.expira_em, ip=r.ip, user_agent=r.user_agent, atual=r.token_hash == atual_hash) for r in rows]  # type: ignore[arg-type]


@router.post("/sessoes/revogar-outras")
async def revogar_outras(request: Request, usuario: Usuario = Depends(usuario_atual), session: Session = Depends(get_session)) -> dict:
    if usuario is not _LOCAL and not csrf_ok(request):
        raise HTTPException(403, "requisição recusada (CSRF)")
    n = svc.revogar_todas(session, usuario.id, exceto_token=request.cookies.get(COOKIE))  # type: ignore[arg-type]
    svc.registrar(session, "sessoes_revogadas", email=usuario.email, ip=ip_do_cliente(request), detalhe=f"{n} sessões")
    return {"ok": True, "revogadas": n}


# ------------------------------------------------------------------ administração (só admin)
@router.get("/usuarios", response_model=list[UsuarioOut])
async def listar_usuarios(_: Usuario = Depends(exigir_admin), session: Session = Depends(get_session)) -> list[UsuarioOut]:
    return [_out(u) for u in session.exec(select(Usuario).order_by(Usuario.email)).all()]


@router.post("/usuarios", response_model=UsuarioOut, status_code=201)
async def criar_usuario(dados: UsuarioIn, admin: Usuario = Depends(exigir_admin), session: Session = Depends(get_session)) -> UsuarioOut:
    try:
        return _out(svc.criar_usuario(session, email=dados.email, nome=dados.nome, papel=dados.papel, telegram_chat_id=dados.telegram_chat_id, por=admin.email))
    except svc.AuthErro as exc:
        raise HTTPException(exc.status, exc.detalhe) from exc


@router.patch("/usuarios/{usuario_id}", response_model=UsuarioOut)
async def alterar_usuario(usuario_id: int, dados: UsuarioPatch, admin: Usuario = Depends(exigir_admin), session: Session = Depends(get_session)) -> UsuarioOut:
    u = session.get(Usuario, usuario_id)
    if u is None:
        raise HTTPException(404, "usuário não encontrado")
    try:
        return _out(svc.alterar_usuario(session, u, por=admin, **dados.model_dump(exclude_unset=True)))
    except svc.AuthErro as exc:
        raise HTTPException(exc.status, exc.detalhe) from exc


@router.delete("/usuarios/{usuario_id}", status_code=204)
async def remover_usuario(usuario_id: int, admin: Usuario = Depends(exigir_admin), session: Session = Depends(get_session)) -> Response:
    u = session.get(Usuario, usuario_id)
    if u is None:
        raise HTTPException(404, "usuário não encontrado")
    try:
        svc.remover_usuario(session, u, por=admin)
    except svc.AuthErro as exc:
        raise HTTPException(exc.status, exc.detalhe) from exc
    return Response(status_code=204)


@router.get("/eventos", response_model=list[EventoOut])
async def eventos(limit: int = 100, email: str | None = None, _: Usuario = Depends(exigir_admin), session: Session = Depends(get_session)) -> list[EventoOut]:
    q = select(EventoAcesso).order_by(EventoAcesso.id.desc()).limit(max(1, min(limit, 500)))  # type: ignore[attr-defined]
    if email:
        q = q.where(EventoAcesso.email == email.strip().lower())
    return [EventoOut.model_validate(e, from_attributes=True) for e in session.exec(q).all()]
