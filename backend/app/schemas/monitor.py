from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CanalAlerta = Literal["jsonl", "webhook", "telegram", "nenhum"]
TipoMonitor = Literal["query", "hashtag"]


class MonitorIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    query: str = Field(min_length=1)
    cron: str = "0 */6 * * *"
    canal_alerta: CanalAlerta = "jsonl"
    webhook_url: str | None = None
    tipo: TipoMonitor = "query"
    ativo: bool = True
    radar_modo: Literal["termos", "estrito"] = "termos"


class MonitorPatch(BaseModel):
    nome: str | None = None
    query: str | None = None
    cron: str | None = None
    canal_alerta: CanalAlerta | None = None
    webhook_url: str | None = None
    ativo: bool | None = None
    radar_modo: Literal["termos", "estrito"] | None = None


class MonitorOut(BaseModel):
    id: int
    nome: str
    query: str
    cron: str
    canal_alerta: str
    webhook_url: str | None
    tipo: str
    ativo: bool
    ultima_execucao: datetime | None
    proxima_execucao: datetime | None
    criado_em: datetime
    # Radar (aditivo): modo de casamento e contagem de hits
    radar_modo: str = "termos"
    hits_total: int = 0
    hits_novos: int = 0


class MonitorRunOut(BaseModel):
    id: int
    monitor_id: int
    executado_em: datetime
    status: str
    deeplinks: dict[str, str]
    resultado: dict[str, Any]
    log: str
