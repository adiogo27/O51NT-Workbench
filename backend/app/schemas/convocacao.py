from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Estado = Literal["nova", "confirmada", "descartada"]
Severidade = Literal["baixa", "media", "alta", "critica"]
TipoFonte = Literal["bluesky_busca", "telegram_canal", "searxng_imagens", "feed_midia"]


class DeteccaoOut(BaseModel):
    id: int
    origem: str
    plataforma: str
    post_url: str
    imagem_url: str
    autor: str
    publicado_em: datetime | None
    evidencia_id: int | None
    sha256: str
    phash: str
    texto_post: str
    texto_ocr: str
    ocr_confianca: float
    ocr_modelo: str
    qr: list[str] = []
    convites: list[dict[str, str]] = []
    termos_lexico: dict[str, list[str]] = {}
    termos_monitor: str
    monitor_ids: str
    tempo: str
    data_evento: date | None
    hora_evento: str | None
    local_evento: str
    noticiando: bool
    nao_pacifico: bool
    score: int
    score_detalhe: dict[str, Any] = {}
    severidade: str
    estado: str
    referencia_id: int | None
    alerta_id: int | None
    boletim_item_id: int | None
    agenda_evento_id: int | None
    ocorrencias: int
    notas: str
    criado_em: datetime


class AnaliseOut(BaseModel):
    deteccao: DeteccaoOut | None
    nova: bool
    duplicada: bool
    salva: bool
    score: int
    severidade: str
    alerta_id: int | None
    ocorrencia_id: int | None
    resultado: dict[str, Any]  # decomposição, léxico, OCR, QR, convites, capacidades


class DeteccaoPatch(BaseModel):
    estado: Estado | None = None
    notas: str | None = Field(default=None, max_length=5000)


class OcorrenciaOut(BaseModel):
    id: int
    deteccao_id: int
    post_url: str
    imagem_url: str
    plataforma: str
    autor: str
    publicado_em: datetime | None
    visto_em: datetime
    variante: bool
    fonte_id: int | None


class ReferenciaOut(BaseModel):
    id: int
    deteccao_id: int | None
    evidencia_id: int | None
    phash: str
    tem_embedding: bool
    modelo_embedding: str
    rotulo: str
    notas: str
    criado_em: datetime


class ConfirmarIn(BaseModel):
    rotulo: str = Field(default="", max_length=200)


class DescartarIn(BaseModel):
    motivo: str = Field(default="", max_length=500)


class BoletimIn(BaseModel):
    data: date | None = None
    secao: Literal["noticia", "fake_news", "manifestacao", "imagem_institucional", "outro"] = "manifestacao"


class AgendaIn(BaseModel):
    candidato: str = Field(default="—", max_length=120)
    titulo: str | None = Field(default=None, max_length=200)
    data: date | None = None
    cidade: str | None = None
    uf: str | None = Field(default=None, max_length=2)


class FonteConvocacaoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    tipo: TipoFonte
    parametro: str = Field(default="", max_length=500)
    rede_alvo: str = Field(default="", max_length=30)
    ativa: bool = True
    respeitar_robots: bool = True


class FonteConvocacaoPatch(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    parametro: str | None = Field(default=None, max_length=500)
    rede_alvo: str | None = None
    ativa: bool | None = None
    respeitar_robots: bool | None = None


class FonteConvocacaoOut(BaseModel):
    id: int
    nome: str
    tipo: str
    parametro: str
    rede_alvo: str
    ativa: bool
    respeitar_robots: bool
    ultima_coleta: datetime | None
    ultimo_status: int
    ultimo_erro: str
    itens_total: int
    novos_ultima: int
    criado_em: datetime


class FonteTesteIn(BaseModel):
    tipo: TipoFonte
    parametro: str = Field(default="", max_length=500)
    respeitar_robots: bool = True


class FonteTesteOut(BaseModel):
    ok: bool
    status: int
    erro: str | None
    robots_permite: bool
    candidatos: int
    com_imagem: int
    amostra: list[dict[str, Any]]


class StatusOut(BaseModel):
    ativo: bool
    intervalo_min: int
    agendado: bool
    proximo_ciclo: datetime | None
    ultimo_ciclo: dict[str, Any] | None
    fontes_ativas: int
    fontes_total: int
    deteccoes_total: int
    novas: int
    por_severidade: dict[str, int]
    referencias: int
    capacidades: dict[str, Any]
