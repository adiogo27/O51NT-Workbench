from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models._base import agora


class QueryTemplate(SQLModel, table=True):
    __tablename__ = "query_template"

    id: int | None = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    categoria: str = "geral"
    descricao: str = ""
    query: str
    placeholders: str = ""  # lista separada por "|", ex.: "Termo|2026-10-01"
    origem_pdf: bool = False
    criado_em: datetime = Field(default_factory=agora)
