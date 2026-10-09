"""Porteiro da API: exige sessão válida em /api/* quando a autenticação está ativa (O51NT_ADMIN_EMAIL definido).

Isenções: SPA e assets (o bundle não contém dados), /api/health, /api/version, /api/auth/*, e acesso local direto
(cliente 127.0.0.1/::1 SEM cabeçalho X-Forwarded-For — automações da própria máquina, como o OpenClaw; o Caddy
sempre envia X-Forwarded-For, então o tráfego da internet nunca cai nesta isenção).
Anti-CSRF nas requisições que alteram estado: cookie SameSite=Strict + cabeçalho `X-Requested-With: O51NT` +
recusa de `Sec-Fetch-Site: cross-site`.
"""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings
from app.db import get_engine
from app.services import auth as auth_svc

COOKIE = "o51nt_sessao"
HEADER_CSRF = "x-requested-with"
VALOR_CSRF = "O51NT"
ISENTOS = ("/api/health", "/api/version")
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


def ip_do_cliente(request: Request) -> str:
    """IP real: X-Real-IP (posto pelo Caddy a partir de {client_ip}), senão 1º X-Forwarded-For, senão o socket."""
    h = request.headers
    if h.get("x-real-ip"):
        return h["x-real-ip"].strip()[:45]
    if h.get("x-forwarded-for"):
        return h["x-forwarded-for"].split(",")[0].strip()[:45]
    return (request.client.host if request.client else "")[:45]


def acesso_local_direto(scope: Scope) -> bool:
    cliente = scope.get("client")
    host = cliente[0] if cliente else ""
    if host not in ("127.0.0.1", "::1"):
        return False
    return not any(k in (b"x-forwarded-for", b"x-real-ip") for k, _ in scope.get("headers", []))


def _resposta(status: int, detalhe: str, extra: dict[str, Any] | None = None) -> tuple[int, bytes]:
    return status, json.dumps({"detail": detalhe, **(extra or {})}, ensure_ascii=False).encode()


class AuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not get_settings().auth_enabled:
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        if not path.startswith("/api/") or path in ISENTOS or path.startswith("/api/auth/") or acesso_local_direto(scope):
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        token = request.cookies.get(COOKIE)
        par = await run_in_threadpool(_validar, token)
        if par is None:
            await _enviar(send, *_resposta(401, "não autenticado", {"auth": True}))
            return
        if request.method not in METODOS_SEGUROS and not csrf_ok(request):
            await _enviar(send, *_resposta(403, "requisição recusada (CSRF)"))
            return
        scope.setdefault("state", {})
        scope["state"]["usuario"] = par[1]
        scope["state"]["sessao_token"] = token
        await self.app(scope, receive, send)


def csrf_ok(request: Request) -> bool:
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        return False
    return request.headers.get(HEADER_CSRF) == VALOR_CSRF


def _validar(token: str | None) -> tuple[Any, Any] | None:
    with Session(get_engine()) as session:
        par = auth_svc.obter_sessao(session, token)
        if par is None:
            return None
        sessao, usuario = par
        session.expunge(usuario)
        return sessao.id, usuario


async def _enviar(send: Send, status: int, corpo: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store"), (b"content-length", str(len(corpo)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": corpo})
