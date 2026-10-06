from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models._base import agora


class Invite(SQLModel, table=True):
    __tablename__ = "invite"

    id: int | None = Field(default=None, primary_key=True)
    plataforma: str = Field(index=True)  # whatsapp | telegram
    url: str = Field(index=True, unique=True)
    termo: str = ""
    origem: str = ""  # URL da página de resultados onde foi encontrado
    first_seen: datetime = Field(default_factory=agora)
    last_seen: datetime = Field(default_factory=agora)
    hash_conteudo: str = ""
