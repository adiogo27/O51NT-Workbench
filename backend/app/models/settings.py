from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    # Convocações (detector de cartazes/postagens de convocação)
    convocacoesAtivo: bool = False  # coletor agendado desligado até o analista ligar
    convocacoesIntervaloMin: int = Field(default=30, ge=5, le=1440)
    convocacoesPerfilML: Literal["leve", "completo"] = "leve"  # completo = CLIP (requer ./run.sh --ml)
    convocacoesLimiarAlerta: int = Field(default=55, ge=1, le=100)
    convocacoesLimiarCritico: int = Field(default=75, ge=1, le=100)
    convocacoesPesoLexico: float = Field(default=0.45, ge=0, le=1)
    convocacoesPesoVisual: float = Field(default=0.20, ge=0, le=1)
    convocacoesPesoReferencia: float = Field(default=0.20, ge=0, le=1)
    convocacoesPesoMonitor: float = Field(default=0.15, ge=0, le=1)
    convocacoesBonusDistribuicao: int = Field(default=15, ge=0, le=50)
    convocacoesTermosExtra: list[str] = []
    convocacoesTermosExcluir: list[str] = []
    convocacoesMaxImagensCiclo: int = Field(default=40, ge=1, le=500)
    convocacoesDescarregarMin: int = Field(default=10, ge=1, le=240)
    convocacoesAnalisarFeeds: bool = True
    convocacoesCanalAlerta: Literal["jsonl", "webhook", "nenhum"] = "jsonl"
    convocacoesWebhookUrl: str | None = None
    convocacoesRetencaoDias: int = Field(default=180, ge=0, le=36500)  # poda detecções descartadas; 0 = nunca
    # Convites
    convitesRespeitarRobots: bool = True
    convitesVerificarAuto: bool = False
    convitesVerificarIntervaloHoras: int = Field(default=24, ge=1, le=720)

    @model_validator(mode="after")
    def _limiares(self) -> "Preferencias":
        if self.convocacoesLimiarCritico <= self.convocacoesLimiarAlerta:
            raise ValueError("convocacoesLimiarCritico deve ser maior que convocacoesLimiarAlerta")
        return self


class AppSettings(BaseModel):
    """Settings do usuário persistidos em data/settings.json (não é tabela)."""

    tema: Tema = Tema()
    tipografia: Tipografia = Tipografia()
    preferencias: Preferencias = Preferencias()
