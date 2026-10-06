from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.models._base import agora


class Perfil(SQLModel, table=True):
    """Perfil público para acompanhar (seções 'Perfis relevantes' / 'Perfis para acompanhar' do boletim)."""

    __tablename__ = "perfil"
    __table_args__ = (UniqueConstraint("rede", "handle"),)

    id: int | None = Field(default=None, primary_key=True)
    rede: str = Field(index=True)  # x | instagram | facebook | tiktok | youtube | telegram | mastodon | site | outro
    handle: str = Field(index=True)  # sem '@' (mastodon: usuario@instancia; site: a própria URL)
    url: str
    rotulo: str = ""
    categoria: str = "outro"  # candidato | partido | institucional | midia | coletivo | outro
    notas: str = ""
    ativo: bool = True
    monitor_id: int | None = None
    criado_em: datetime = Field(default_factory=agora)


class BoletimItem(SQLModel, table=True):
    """Item curado do boletim diário (notícia, fake news, manifestação, imagem institucional…)."""

    __tablename__ = "boletim_item"

    id: int | None = Field(default=None, primary_key=True)
    data: date = Field(index=True)
    secao: str = Field(index=True)  # noticia | fake_news | manifestacao | imagem_institucional | hashtag | grupo | perfil | outro
    titulo: str
    url: str = ""
    fonte: str = ""
    resumo: str = ""
    evidence_id: int | None = Field(default=None, foreign_key="evidence.id", ondelete="SET NULL")
    criado_em: datetime = Field(default_factory=agora)
