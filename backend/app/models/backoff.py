from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models._base import agora


class DomainBackoff(SQLModel, table=True):
    """Domínios que responderam 403/429: não são contatados até `retry_after` (TTL 1h → 6h → 24h)."""

    __tablename__ = "domain_backoff"

    domain: str = Field(primary_key=True)
    retry_after: datetime
    nivel: int = 1  # 1 = 1h, 2 = 6h, 3+ = 24h
    ultimo_status: int = 0
    atualizado_em: datetime = Field(default_factory=agora)
