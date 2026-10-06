from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.models._base import agora


class Hashtag(SQLModel, table=True):
    __tablename__ = "hashtag"
    __table_args__ = (UniqueConstraint("tag", "rede"),)

    id: int | None = Field(default=None, primary_key=True)
    tag: str = Field(index=True)  # forma original, como exibida (ex.: #Eleições2026)
    chave_normalizada: str = Field(default="", index=True)  # sem acentos e casefold (ex.: #eleicoes2026)
    rede: str = "x"
    contagem: int = 0
    primeira_vez: datetime = Field(default_factory=agora)
    ultima_vez: datetime = Field(default_factory=agora)
    fonte: str = "manual"
    monitor_id: int | None = None


class HashtagSnapshot(SQLModel, table=True):
    """Série temporal simples para o gráfico (uma linha por coleta)."""

    __tablename__ = "hashtag_snapshot"

    id: int | None = Field(default=None, primary_key=True)
    hashtag_id: int = Field(foreign_key="hashtag.id", index=True, ondelete="CASCADE")
    coletado_em: datetime = Field(default_factory=agora, index=True)
    contagem: int = 0
    fonte: str = ""
    origem_url: str = ""
    sha256: str = ""
