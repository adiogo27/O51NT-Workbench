from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Rede = Literal["x", "instagram", "facebook", "tiktok", "youtube", "telegram", "mastodon", "site", "outro"]
CategoriaPerfil = Literal["candidato", "partido", "institucional", "midia", "coletivo", "outro"]
Secao = Literal["noticia", "fake_news", "manifestacao", "imagem_institucional", "hashtag", "grupo", "perfil", "outro"]


def _val_url_opcional(v: str | None) -> str:
    v = (v or "").strip()
    if v and not v.startswith(("http://", "https://")):
        raise ValueError("url deve começar com http:// ou https://")
    return v


class PerfilIn(BaseModel):
    rede: Rede
    handle: str = Field(min_length=1, max_length=300, description="@usuario, usuario ou URL do perfil")
    rotulo: str = Field(default="", max_length=120)
    categoria: CategoriaPerfil = "outro"
    notas: str = Field(default="", max_length=2000)
    ativo: bool = True


class PerfilPatch(BaseModel):
    rotulo: str | None = Field(default=None, max_length=120)
    categoria: CategoriaPerfil | None = None
    notas: str | None = Field(default=None, max_length=2000)
    ativo: bool | None = None


class PerfilOut(BaseModel):
    id: int
    rede: str
    handle: str
    url: str
    rotulo: str
    categoria: str
    notas: str
    ativo: bool
    monitor_id: int | None
    criado_em: datetime


class PerfilDeeplinksOut(BaseModel):
    perfil: str
    query_mencoes: str
    query_mencoes_x: str
    deeplinks: dict[str, str]
    deeplinks_x: dict[str, str]


class PerfilMonitorIn(BaseModel):
    cron: str = "0 */3 * * *"
    canal_alerta: Literal["jsonl", "webhook", "telegram", "nenhum"] = "jsonl"
    webhook_url: str | None = None
    usar_x: bool | None = None  # None → X se o perfil for do X


class BoletimItemIn(BaseModel):
    data: date
    secao: Secao
    titulo: str = Field(min_length=1, max_length=300)
    url: str = ""
    fonte: str = Field(default="", max_length=120)
    resumo: str = Field(default="", max_length=3000)
    evidence_id: int | None = None

    _url = field_validator("url")(classmethod(lambda cls, v: _val_url_opcional(v)))  # type: ignore[arg-type]


class BoletimItemPatch(BaseModel):
    data: date | None = None
    secao: Secao | None = None
    titulo: str | None = Field(default=None, min_length=1, max_length=300)
    url: str | None = None
    fonte: str | None = Field(default=None, max_length=120)
    resumo: str | None = Field(default=None, max_length=3000)
    evidence_id: int | None = None

    _url = field_validator("url")(classmethod(lambda cls, v: None if v is None else _val_url_opcional(v)))  # type: ignore[arg-type]


class BoletimItemOut(BaseModel):
    id: int
    data: date
    secao: Secao
    titulo: str
    url: str
    fonte: str
    resumo: str
    evidence_id: int | None
    criado_em: datetime


class BoletimOut(BaseModel):
    data: date
    titulo: str
    dia_semana: str
    secoes: dict[str, list[BoletimItemOut]]
    agenda: dict[str, Any]
    perfis: list[PerfilOut]
    hashtags: list[dict[str, Any]]
    convites: list[dict[str, Any]]
    markdown: str
