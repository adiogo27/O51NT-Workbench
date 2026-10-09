"""Autenticação do painel: usuários autorizados, códigos de acesso por e-mail, sessões e trilha de auditoria.

Nenhum segredo fica em claro: códigos e tokens de sessão são guardados como HMAC-SHA256 (pepper em data/auth_secret).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlmodel import Field, SQLModel

from app.models._base import agora

Papel = Literal["admin", "analista"]


class Usuario(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)  # sempre minúsculo
    nome: str = ""
    papel: str = "analista"  # admin | analista
    ativo: bool = True
    telegram_chat_id: str | None = None  # canal alternativo para o código quando não há SMTP
    criado_em: datetime = Field(default_factory=agora)
    criado_por: str = ""  # e-mail de quem cadastrou ("sistema" para o admin inicial)
    ultimo_login: datetime | None = None


class CodigoAcesso(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int = Field(index=True, foreign_key="usuario.id")
    codigo_hash: str
    criado_em: datetime = Field(default_factory=agora)
    expira_em: datetime
    tentativas: int = 0
    usado_em: datetime | None = None
    invalidado: bool = False
    ip: str = ""
    canal: str = ""  # email | telegram | journal


class Sessao(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    token_hash: str = Field(index=True, unique=True)
    usuario_id: int = Field(index=True, foreign_key="usuario.id")
    criado_em: datetime = Field(default_factory=agora)
    expira_em: datetime
    ultimo_uso: datetime = Field(default_factory=agora)
    ip: str = ""
    user_agent: str = ""
    revogada: bool = False


class EventoAcesso(SQLModel, table=True):
    """Auditoria: cada pedido de código, tentativa de login, logout e ação administrativa."""

    id: int | None = Field(default=None, primary_key=True)
    em: datetime = Field(default_factory=agora, index=True)
    evento: str = Field(index=True)  # codigo_solicitado | login_ok | login_falha | bloqueado | logout | usuario_criado ...
    email: str = Field(default="", index=True)
    ip: str = Field(default="", index=True)
    ok: bool = True
    detalhe: str = ""
