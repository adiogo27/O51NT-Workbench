from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models._base import agora


class QueryHistory(SQLModel, table=True):
    __tablename__ = "query_history"

    id: int | None = Field(default=None, primary_key=True)
    query: str
    motor: str = "google"
    origem: str = "builder"
    criado_em: datetime = Field(default_factory=agora, index=True)
