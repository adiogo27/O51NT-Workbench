from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.models._base import agora


class Deteccao(SQLModel, table=True):
    """Imagem/post analisado pelo módulo Convocações (uma por imagem única; repostagens viram DeteccaoOcorrencia)."""

    __tablename__ = "deteccao"

    id: int | None = Field(default=None, primary_key=True)
    origem: str = Field(default="manual", index=True)  # manual | url | bluesky | telegram | searxng_imagens | feed
    plataforma: str = Field(default="desconhecida", index=True)  # x | instagram | facebook | bluesky | telegram | mastodon | web | desconhecida
    post_url: str = ""
    imagem_url: str = ""
    autor: str = ""
    publicado_em: datetime | None = None
    evidencia_id: int | None = Field(default=None, foreign_key="evidence.id", ondelete="SET NULL")
    sha256: str = Field(default="", index=True)
    phash: str = Field(default="", index=True)
    dhash: str = ""
    texto_post: str = ""
    texto_ocr: str = ""
    ocr_confianca: float = 0.0
    ocr_modelo: str = ""
    qr_json: str = "[]"
    convites_json: str = "[]"
    termos_lexico_json: str = "{}"
    termos_monitor: str = ""  # "nome: t1 | t2 ; nome2: t3"
    monitor_ids: str = ""  # "1,4"
    tempo: str = "indefinido"  # futuro | passado | indefinido
    data_evento: date | None = Field(default=None, index=True)
    hora_evento: str | None = None
    local_evento: str = ""
    noticiando: bool = False
    nao_pacifico: bool = Field(default=False, index=True)
    score: int = Field(default=0, index=True)
    score_detalhe_json: str = "{}"
    severidade: str = Field(default="baixa", index=True)  # baixa | media | alta | critica
    estado: str = Field(default="nova", index=True)  # nova | confirmada | descartada
    referencia_id: int | None = None
    alerta_id: int | None = None
    boletim_item_id: int | None = None
    agenda_evento_id: int | None = None
    ocorrencias: int = 1
    notas: str = ""
    criado_em: datetime = Field(default_factory=agora, index=True)


class DeteccaoOcorrencia(SQLModel, table=True):
    """Onde mais a mesma imagem (ou variante próxima) apareceu — propagação entre plataformas."""

    __tablename__ = "deteccao_ocorrencia"
    __table_args__ = (UniqueConstraint("post_url"),)

    id: int | None = Field(default=None, primary_key=True)
    deteccao_id: int = Field(foreign_key="deteccao.id", index=True, ondelete="CASCADE")
    post_url: str
    imagem_url: str = ""
    plataforma: str = "desconhecida"
    autor: str = ""
    publicado_em: datetime | None = None
    visto_em: datetime = Field(default_factory=agora)
    variante: bool = False  # True quando casou por pHash (não pelo sha256)
    phash: str = ""
    fonte_id: int | None = None


class ReferenciaCartaz(SQLModel, table=True):
    """Cartaz confirmado pelo analista: vira referência para similaridade (pHash e, no perfil completo, embedding CLIP)."""

    __tablename__ = "referencia_cartaz"

    id: int | None = Field(default=None, primary_key=True)
    deteccao_id: int | None = Field(default=None, index=True)
    evidencia_id: int | None = Field(default=None, foreign_key="evidence.id", ondelete="SET NULL")
    phash: str = Field(default="", index=True)
    dhash: str = ""
    embedding: bytes | None = None  # float32 (512,) ou None
    modelo_embedding: str = ""
    rotulo: str = ""
    notas: str = ""
    criado_em: datetime = Field(default_factory=agora)


class FonteConvocacao(SQLModel, table=True):
    """Fonte do coletor de convocações (separada de `fonte`, que é só RSS/Atom do Radar)."""

    __tablename__ = "fonte_convocacao"
    __table_args__ = (UniqueConstraint("tipo", "parametro"),)

    id: int | None = Field(default=None, primary_key=True)
    nome: str
    tipo: str = Field(index=True)  # bluesky_busca | telegram_canal | searxng_imagens | feed_midia
    parametro: str = ""  # termo | canal | dork | (vazio para feed_midia)
    rede_alvo: str = ""  # x | instagram | facebook | bluesky | telegram | mastodon | web
    ativa: bool = Field(default=True, index=True)
    respeitar_robots: bool = True
    ultima_coleta: datetime | None = None
    ultimo_status: int = 0
    ultimo_erro: str = ""
    itens_total: int = 0
    novos_ultima: int = 0
    cursor: str = ""
    criado_em: datetime = Field(default_factory=agora)
