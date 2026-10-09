from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.agenda import normalizar_rodovia

TipoEvento = Literal["caminhada", "carreata", "motociata", "comicio", "ato", "debate", "entrevista", "reuniao", "outro"]
StatusEvento = Literal["previsto", "confirmado", "cancelado", "realizado"]
Cargo = Literal["presidente", "governador", "senador", "deputado", "outro"]

UFS: frozenset[str] = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)
_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _val_uf(v: str | None) -> str:
    v = (v or "").strip().upper()
    if v and v not in UFS:
        raise ValueError("UF inválida (use a sigla, ex.: SP)")
    return v


def _val_hora(v: str | None) -> str | None:
    v = (v or "").strip()
    if not v:
        return None
    if not _HORA.match(v):
        raise ValueError("hora deve estar no formato HH:MM")
    return v


def _val_rodovias(v: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in v or []:
        norm = normalizar_rodovia(item)
        if norm is None:
            raise ValueError(f"rodovia inválida: '{item}' (use BR-116, BR 116 ou BR116)")
        if norm not in out:
            out.append(norm)
    return out


def _val_url(v: str | None) -> str | None:
    v = (v or "").strip()
    if not v:
        return None
    if not v.startswith(("http://", "https://")):
        raise ValueError("fonte_url deve começar com http:// ou https://")
    return v


class AgendaEventoIn(BaseModel):
    candidato: str = Field(min_length=1, max_length=120)
    partido: str = Field(default="", max_length=40)
    cargo: Cargo = "presidente"
    titulo: str = Field(min_length=1, max_length=200)
    tipo: TipoEvento = "outro"
    data: date
    hora_inicio: str | None = None
    hora_fim: str | None = None
    cidade: str = Field(default="", max_length=120)
    uf: str = ""
    local: str = Field(default="", max_length=200)
    rodovias: list[str] = Field(default_factory=list)
    impacto_rodovia: bool = False
    descricao: str = Field(default="", max_length=2000)
    fonte_url: str | None = None
    status: StatusEvento = "previsto"

    _uf = field_validator("uf")(classmethod(lambda cls, v: _val_uf(v)))  # type: ignore[arg-type]
    _horas = field_validator("hora_inicio", "hora_fim")(classmethod(lambda cls, v: _val_hora(v)))  # type: ignore[arg-type]
    _rod = field_validator("rodovias")(classmethod(lambda cls, v: _val_rodovias(v)))  # type: ignore[arg-type]
    _url = field_validator("fonte_url")(classmethod(lambda cls, v: _val_url(v)))  # type: ignore[arg-type]


class AgendaEventoPatch(BaseModel):
    candidato: str | None = Field(default=None, min_length=1, max_length=120)
    partido: str | None = Field(default=None, max_length=40)
    cargo: Cargo | None = None
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    tipo: TipoEvento | None = None
    data: date | None = None
    hora_inicio: str | None = None
    hora_fim: str | None = None
    cidade: str | None = Field(default=None, max_length=120)
    uf: str | None = None
    local: str | None = Field(default=None, max_length=200)
    rodovias: list[str] | None = None
    impacto_rodovia: bool | None = None
    descricao: str | None = Field(default=None, max_length=2000)
    fonte_url: str | None = None
    status: StatusEvento | None = None

    _uf = field_validator("uf")(classmethod(lambda cls, v: None if v is None else _val_uf(v)))  # type: ignore[arg-type]
    _horas = field_validator("hora_inicio", "hora_fim")(classmethod(lambda cls, v: _val_hora(v)))  # type: ignore[arg-type]
    _rod = field_validator("rodovias")(classmethod(lambda cls, v: None if v is None else _val_rodovias(v)))  # type: ignore[arg-type]
    _url = field_validator("fonte_url")(classmethod(lambda cls, v: _val_url(v)))  # type: ignore[arg-type]


class AgendaEventoOut(BaseModel):
    id: int
    candidato: str
    partido: str
    cargo: str
    titulo: str
    tipo: str
    data: date
    dia_semana: str
    hora_inicio: str | None
    hora_fim: str | None
    cidade: str
    uf: str
    local: str
    rodovias: list[str]
    impacto_rodovia: bool
    descricao: str
    fonte_url: str | None
    status: str
    monitor_id: int | None
    criado_em: datetime
    atualizado_em: datetime


class AgendaDiaOut(BaseModel):
    data: date
    dia_semana: str
    total: int
    com_impacto_rodovia: int
    por_candidato: dict[str, list[AgendaEventoOut]]
    eventos: list[AgendaEventoOut]


class AgendaQueriesOut(BaseModel):
    evento_id: int
    query: str
    query_x: str
    deeplinks: dict[str, str]
    deeplinks_x: dict[str, str]
    termos_rodovia: list[str]


class AgendaMonitorIn(BaseModel):
    cron: str = "0 */2 * * *"
    canal_alerta: Literal["jsonl", "webhook", "telegram", "nenhum"] = "jsonl"
    webhook_url: str | None = None
    usar_x: bool = False
