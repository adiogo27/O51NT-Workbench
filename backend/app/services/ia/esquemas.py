"""Contratos JSON de cada etapa do pipeline (validados com pydantic; resposta fora do esquema = erro da etapa)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Veredito = Literal["RELEVANTE", "OBSERVAR", "DESCARTAR"]
Severidade = Literal["baixa", "media", "alta", "critica"]
Secao = Literal["noticia", "fake_news", "manifestacao", "imagem_institucional", "outro"]
ORDEM_SEVERIDADE = {"baixa": 0, "media": 1, "alta": 2, "critica": 3}


def _txt(v: object, max_len: int) -> str:
    return " ".join(str(v or "").split())[:max_len]


class TriagemOut(BaseModel):
    """Saída do agent `sentinela`."""

    model_config = ConfigDict(extra="ignore")

    veredito: Veredito
    severidade: Severidade = "media"
    justificativa: str = ""
    acao_sugerida: str = ""
    secao: Secao | None = None
    eh_evento: bool = False
    desinformacao: bool = False
    tags: list[str] = Field(default_factory=list)

    @field_validator("veredito", mode="before")
    @classmethod
    def _up(cls, v: object) -> object:
        return str(v).strip().upper() if isinstance(v, str) else v

    @field_validator("severidade", mode="before")
    @classmethod
    def _sev(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip().lower().replace("é", "e").replace("í", "i")
            return {"critico": "critica", "medio": "media", "alto": "alta", "baixo": "baixa"}.get(s, s)
        return v

    @field_validator("justificativa", "acao_sugerida", mode="before")
    @classmethod
    def _curto(cls, v: object) -> str:
        return _txt(v, 600)

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, v: object) -> list[str]:
        if isinstance(v, str):
            v = [t for t in v.split(",")]
        return [_txt(t, 40) for t in (v or []) if str(t).strip()][:10]


class EventoOut(BaseModel):
    """Saída do agent `extrator` (esquema `o51nt-esquema`)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    tipo: str | None = None  # ato | carreata | bloqueio | motociata | greve | outro
    titulo: str | None = None
    data: str | None = None  # AAAA-MM-DD
    hora: str | None = None  # HH:MM
    cidade: str | None = None
    uf: str | None = None
    local: str | None = None
    rodovias: list[str] = Field(default_factory=list)
    rota: str | None = None
    organizador: str | None = None
    pauta: str | None = None
    canais: list[str] = Field(default_factory=list)
    impacto_rodovia_federal: bool = False
    confianca: float = 0.0
    notas: str = Field(default="", alias="_notas")

    @field_validator("rodovias", "canais", mode="before")
    @classmethod
    def _lista(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            v = v.split(",")
        return [_txt(x, 40) for x in v if str(x).strip()][:12]

    @field_validator("confianca", mode="before")
    @classmethod
    def _conf(cls, v: object) -> float:
        try:
            f = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, f / 100 if f > 1 else f))

    @field_validator("tipo", "titulo", "data", "hora", "cidade", "uf", "local", "rota", "organizador", "pauta", mode="before")
    @classmethod
    def _opc(cls, v: object) -> str | None:
        if v is None:
            return None
        t = _txt(v, 500)
        return t or None

    @field_validator("notas", mode="before")
    @classmethod
    def _notas(cls, v: object) -> str:
        return _txt(v, 500)


class FontePesquisa(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str
    titulo: str = ""
    trecho: str = ""

    @field_validator("titulo", "trecho", mode="before")
    @classmethod
    def _curto(cls, v: object) -> str:
        return _txt(v, 400)


class PesquisaOut(BaseModel):
    """Saída do agent `pesquisador`."""

    model_config = ConfigDict(extra="ignore")

    resposta: str = ""
    fontes: list[FontePesquisa] = Field(default_factory=list)
    confianca: float = 0.0
    lacunas: str = ""
    verificacao: Literal["confirmado", "parcial", "nao_confirmado", "falso"] | None = None

    @field_validator("resposta", "lacunas", mode="before")
    @classmethod
    def _curto(cls, v: object) -> str:
        return _txt(v, 4000)

    @field_validator("fontes", mode="before")
    @classmethod
    def _fontes(cls, v: object) -> list:
        out = []
        for f in v or []:
            if isinstance(f, str) and f.startswith(("http://", "https://")):
                out.append({"url": f})
            elif isinstance(f, dict) and str(f.get("url", "")).startswith(("http://", "https://")):
                out.append(f)
        return out[:12]

    @field_validator("confianca", mode="before")
    @classmethod
    def _conf(cls, v: object) -> float:
        try:
            f = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, f / 100 if f > 1 else f))


class CartaoOut(BaseModel):
    """Saída do agent `analista` (cartão final: Telegram, inbox, rascunho de boletim)."""

    model_config = ConfigDict(extra="ignore")

    titulo: str
    resumo: str = ""
    impacto_rodovia: str = ""
    acao: str = ""
    fontes: list[str] = Field(default_factory=list)

    @field_validator("titulo", mode="before")
    @classmethod
    def _tit(cls, v: object) -> str:
        return _txt(v, 200)

    @field_validator("resumo", "impacto_rodovia", "acao", mode="before")
    @classmethod
    def _curto(cls, v: object) -> str:
        return _txt(v, 1500)

    @field_validator("fontes", mode="before")
    @classmethod
    def _urls(cls, v: object) -> list[str]:
        out: list[str] = []
        for f in v or []:
            u = f.get("url") if isinstance(f, dict) else f
            if isinstance(u, str) and u.startswith(("http://", "https://")) and u not in out:
                out.append(u[:500])
        return out[:8]
