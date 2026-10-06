from __future__ import annotations

from pydantic import BaseModel, Field


class Tema(BaseModel):
    primary: str = "#0091d5"
    secondary: str = "#1e293b"
    background: str = "#0b1220"
    foreground: str = "#e2e8f0"
    accent: str = "#f2e08a"
    radius: float = Field(default=0.5, ge=0, le=2)


class Tipografia(BaseModel):
    fontFamily: str = "Inter"
    fontSizeBase: int = Field(default=16, ge=12, le=24)


class Preferencias(BaseModel):
    navegadorPadrao: str = "auto"
    historicoRetencaoDias: int = Field(default=90, ge=0, le=36500)  # 0 = sem limite por idade
    historicoMaxEntradas: int = Field(default=10_000, ge=0, le=1_000_000)  # 0 = sem limite
    radarAtivo: bool = True
    radarIntervaloMin: int = Field(default=10, ge=2, le=1440)


class AppSettings(BaseModel):
    """Settings do usuário persistidos em data/settings.json (não é tabela)."""

    tema: Tema = Tema()
    tipografia: Tipografia = Tipografia()
    preferencias: Preferencias = Preferencias()
