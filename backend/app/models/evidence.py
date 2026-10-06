from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models._base import agora


class Evidence(SQLModel, table=True):
    __tablename__ = "evidence"

    id: int | None = Field(default=None, primary_key=True)
    tipo: str = "arquivo"  # arquivo | imagem | captura | html
    origem_url: str | None = None
    arquivo: str  # caminho relativo dentro de data/evidence
    nome_original: str = ""
    tamanho: int = 0
    mime: str = "application/octet-stream"
    sha256: str = Field(index=True)
    criado_em: datetime = Field(default_factory=agora, index=True)
    notas: str = ""
