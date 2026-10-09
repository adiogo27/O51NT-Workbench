from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models._base import agora


class Monitor(SQLModel, table=True):
    __tablename__ = "monitor"

    id: int | None = Field(default=None, primary_key=True)
    nome: str
    query: str
    cron: str = "0 */6 * * *"
    canal_alerta: str = "jsonl"  # jsonl | webhook | nenhum
    webhook_url: str | None = None
    tipo: str = "query"  # query | hashtag
    radar_modo: str = "termos"  # termos (ignora site: no casamento) | estrito (exige o domínio)
    ia: bool = True  # hits deste monitor entram na fila do assistente de IA (quando iaAtivo)
    ativo: bool = True
    ultima_execucao: datetime | None = None
    proxima_execucao: datetime | None = None
    criado_em: datetime = Field(default_factory=agora)


class MonitorRun(SQLModel, table=True):
    __tablename__ = "monitor_run"

    id: int | None = Field(default=None, primary_key=True)
    monitor_id: int = Field(foreign_key="monitor.id", index=True, ondelete="CASCADE")
    executado_em: datetime = Field(default_factory=agora, index=True)
    status: str = "ok"  # ok | erro
    deeplinks_json: str = "{}"
    resultado_json: str = "{}"
    log: str = ""
