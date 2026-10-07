from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models._base import agora


class Invite(SQLModel, table=True):
    __tablename__ = "invite"

    id: int | None = Field(default=None, primary_key=True)
    plataforma: str = Field(index=True)  # whatsapp | whatsapp_canal | telegram | telegram_publico
    url: str = Field(index=True, unique=True)
    termo: str = ""
    origem: str = ""  # URL da página de resultados onde foi encontrado
    first_seen: datetime = Field(default_factory=agora)
    last_seen: datetime = Field(default_factory=agora)
    hash_conteudo: str = ""
    # v2 — contexto e verificação (GET da página pública de convite; nunca entra no grupo)
    fonte_url: str = ""  # página/post onde o link apareceu
    status: str = Field(default="desconhecido", index=True)  # ativo | revogado | desconhecido
    nome_grupo: str | None = None
    membros: int | None = None  # Telegram expõe; WhatsApp não
    descricao: str | None = None
    verificado_em: datetime | None = None
    evidencia_id: int | None = None  # foto do grupo salva como evidência
    score_relevancia: int = 0
    http_status: int = 0
    erro_verificacao: str = ""
