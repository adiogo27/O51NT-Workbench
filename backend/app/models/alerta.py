from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models._base import agora


class Alerta(SQLModel, table=True):
    """Alerta persistido (inbox da interface). O JSONL/webhook de `services.alerts` continua sendo emitido em paralelo."""

    __tablename__ = "alerta"

    id: int | None = Field(default=None, primary_key=True)
    tipo: str = Field(index=True)  # convocacao | convite | radar
    severidade: str = Field(default="media", index=True)  # baixa | media | alta | critica
    titulo: str
    resumo: str = ""
    url: str = ""
    deteccao_id: int | None = None
    invite_id: int | None = None
    monitor_id: int | None = None
    lido: bool = Field(default=False, index=True)
    criado_em: datetime = Field(default_factory=agora, index=True)
    canal_log: str = ""
