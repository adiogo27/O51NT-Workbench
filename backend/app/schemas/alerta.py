from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AlertaOut(BaseModel):
    id: int
    tipo: str
    severidade: str
    titulo: str
    resumo: str
    url: str
    deteccao_id: int | None
    invite_id: int | None
    monitor_id: int | None
    lido: bool
    criado_em: datetime
    canal_log: str


class AlertaPatch(BaseModel):
    lido: bool
