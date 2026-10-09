from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

CategoriaFonte = Literal["imprensa", "oficial", "rede", "alerta", "outro"]
TipoFonte = Literal["feed", "pagina"]


def _val_url(v: str) -> str:
    v = (v or "").strip()
    if not v.startswith(("http://", "https://")):
        raise ValueError("url deve começar com http:// ou https://")
    return v


class FonteIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=2000)
    categoria: CategoriaFonte = "imprensa"
    ativa: bool = True
    respeitar_robots: bool = True
    tipo: TipoFonte = "feed"  # pagina = HTML de notícias sem RSS (links de matérias extraídos a cada verificação)
    intervalo_min: int | None = Field(default=None, ge=1, le=10080)  # None = intervalo global do Radar

    _url = field_validator("url")(classmethod(lambda cls, v: _val_url(v)))  # type: ignore[arg-type]


class FontePatch(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    categoria: CategoriaFonte | None = None
    ativa: bool | None = None
    respeitar_robots: bool | None = None
    tipo: TipoFonte | None = None
    intervalo_min: int | None = Field(default=None, ge=1, le=10080)


class FonteOut(BaseModel):
    id: int
    nome: str
    url: str
    categoria: str
    ativa: bool
    respeitar_robots: bool
    ultima_coleta: datetime | None
    ultimo_status: int
    ultimo_erro: str
    itens_total: int
    novos_ultima: int
    criado_em: datetime
    tipo: str = "feed"
    intervalo_min: int | None = None
    ultima_mudanca: datetime | None = None


class FonteTesteIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    respeitar_robots: bool = True

    _url = field_validator("url")(classmethod(lambda cls, v: _val_url(v)))  # type: ignore[arg-type]


class FonteTesteOut(BaseModel):
    ok: bool
    status: int
    erro: str | None
    robots_permite: bool
    itens: int
    amostra: list[dict[str, Any]]
    tipo_detectado: str | None = None  # feed | pagina
    feed_descoberto: str | None = None  # RSS anunciado pela página, se houver


class HitOut(BaseModel):
    id: int
    monitor_id: int
    monitor_nome: str = ""
    fonte_id: int | None
    fonte_nome: str
    url: str
    titulo: str
    resumo: str
    publicado_em: datetime | None
    encontrado_em: datetime
    termos: str
    origem: str
    lido: bool
    boletim_item_id: int | None


class HitPatch(BaseModel):
    lido: bool


class HitBoletimIn(BaseModel):
    data: date | None = None
    secao: Literal["noticia", "fake_news", "manifestacao", "imagem_institucional", "outro"] = "noticia"


class ItemOut(BaseModel):
    id: int
    fonte_id: int
    fonte_nome: str = ""
    url: str
    titulo: str
    resumo: str
    publicado_em: datetime | None
    coletado_em: datetime


class RadarStatusOut(BaseModel):
    ativo: bool
    intervalo_min: int
    agendado: bool
    proximo_ciclo: datetime | None
    ultimo_ciclo: dict[str, Any] | None
    fontes_ativas: int
    fontes_total: int
    monitores_ativos: int
    itens_total: int
    hits_total: int
    hits_novos: int
