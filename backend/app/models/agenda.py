from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Field, SQLModel

from app.models._base import agora


class AgendaEvento(SQLModel, table=True):
    """Compromisso de campanha (seção 'Agenda dos candidatos' do boletim Op. Eleições 2026)."""

    __tablename__ = "agenda_evento"

    id: int | None = Field(default=None, primary_key=True)
    candidato: str = Field(index=True)
    partido: str = ""
    cargo: str = "presidente"  # presidente | governador | senador | deputado | outro
    titulo: str
    tipo: str = "outro"  # caminhada | carreata | motociata | comicio | ato | debate | entrevista | reuniao | outro
    data: date = Field(index=True)
    hora_inicio: str | None = None  # "HH:MM"
    hora_fim: str | None = None
    cidade: str = ""
    uf: str = Field(default="", index=True)
    local: str = ""
    rodovias: str = ""  # "BR-116,BR-040" (normalizadas)
    impacto_rodovia: bool = Field(default=False, index=True)
    descricao: str = ""
    fonte_url: str | None = None
    status: str = "previsto"  # previsto | confirmado | cancelado | realizado
    monitor_id: int | None = None
    criado_em: datetime = Field(default_factory=agora)
    atualizado_em: datetime = Field(default_factory=agora)
