from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.models._base import agora


class Fonte(SQLModel, table=True):
    """Feed público (RSS/Atom) coletado pelo Radar: imprensa, órgãos oficiais, Mastodon, Google Alertas."""

    __tablename__ = "fonte"

    id: int | None = Field(default=None, primary_key=True)
    nome: str
    url: str = Field(unique=True, index=True)
    categoria: str = "imprensa"  # imprensa | oficial | rede | alerta | outro
    ativa: bool = Field(default=True, index=True)
    respeitar_robots: bool = True  # False só para feeds pessoais (ex.: Google Alertas), decisão explícita do analista
    ultima_coleta: datetime | None = None
    ultimo_status: int = 0
    ultimo_erro: str = ""
    itens_total: int = 0
    novos_ultima: int = 0
    criado_em: datetime = Field(default_factory=agora)
    # Páginas HTML sem RSS (tipo "pagina"): links de matérias são extraídos a cada verificação.
    tipo: str = "feed"  # feed | pagina
    intervalo_min: int | None = None  # None = intervalo global do Radar; senão só verifica quando vencer
    conteudo_hash: str = ""  # hash do texto visível da última verificação (detecta mudança da página)
    ultima_mudanca: datetime | None = None  # última vez em que o conteúdo da página mudou


class FonteItem(SQLModel, table=True):
    """Item de feed já coletado (cache local; é contra ele que as queries dos monitores são casadas)."""

    __tablename__ = "fonte_item"
    __table_args__ = (UniqueConstraint("fonte_id", "url"),)

    id: int | None = Field(default=None, primary_key=True)
    fonte_id: int = Field(foreign_key="fonte.id", index=True, ondelete="CASCADE")
    url: str = Field(index=True)
    titulo: str = ""
    resumo: str = ""
    publicado_em: datetime | None = Field(default=None, index=True)
    coletado_em: datetime = Field(default_factory=agora, index=True)
    sha256: str = ""
    midias: str = "[]"  # JSON: URLs de imagens (enclosure / media:content) para o módulo Convocações


class MonitorHit(SQLModel, table=True):
    """Resultado real de um monitor: item de fonte que casou com a query (único por monitor+URL)."""

    __tablename__ = "monitor_hit"
    __table_args__ = (UniqueConstraint("monitor_id", "url"),)

    id: int | None = Field(default=None, primary_key=True)
    monitor_id: int = Field(foreign_key="monitor.id", index=True, ondelete="CASCADE")
    item_id: int | None = Field(default=None, foreign_key="fonte_item.id", ondelete="SET NULL")
    fonte_id: int | None = None
    fonte_nome: str = ""
    url: str
    titulo: str = ""
    resumo: str = ""
    publicado_em: datetime | None = None
    encontrado_em: datetime = Field(default_factory=agora, index=True)
    termos: str = ""  # termos da query que casaram, separados por " | "
    origem: str = "radar"  # radar (ciclo) | execucao (run-now / cron do monitor)
    lido: bool = Field(default=False, index=True)
    boletim_item_id: int | None = None
