from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class BlocoPrecisao(BaseModel):
    termos: list[str] = Field(default_factory=list, description="Termos soltos (AND implícito)")
    frases_exatas: list[str] = Field(default_factory=list, description='Viram "frase exata"')
    grupos_or: list[list[str]] = Field(default_factory=list, description="Cada grupo vira (A OR B)")
    excluir: list[str] = Field(default_factory=list, description="Viram -termo")
    curingas: list[list[str]] = Field(default_factory=list, description='Pares [A, B] viram "A * B"')


class BlocoTemporal(BaseModel):
    after: date | None = None
    before: date | None = None


class BlocoEscopo(BaseModel):
    sites: list[str] = Field(default_factory=list, description="Agrupados com OR")
    excluir_sites: list[str] = Field(default_factory=list)
    filetype: str | None = None
    inurl: list[str] = Field(default_factory=list)
    intitle: list[str] = Field(default_factory=list)
    intext: list[str] = Field(default_factory=list)


class BlocoX(BaseModel):
    """Operadores do X/Twitter e TweetDeck (strings do boletim 'Op. Eleições 2026')."""

    since: date | None = None
    until: date | None = None
    from_: list[str] = Field(default_factory=list, alias="from", description="from:usuário (autor)")
    to: list[str] = Field(default_factory=list, description="to:usuário (destinatário)")
    mencoes: list[str] = Field(default_factory=list, description="@usuário")
    excluir_retweets: bool = Field(default=False, description="-is:retweet")
    apenas_respostas: bool = Field(default=False, description="is:reply")
    apenas_verificados: bool = Field(default=False, description="is:verified")
    has: list[str] = Field(default_factory=list, description="has:media|images|videos|links")
    lang: str | None = Field(default=None, description="lang:pt")
    min_faves: int | None = Field(default=None, ge=0)
    min_retweets: int | None = Field(default=None, ge=0)
    min_replies: int | None = Field(default=None, ge=0)

    model_config = {"populate_by_name": True}


class ComposeRequest(BaseModel):
    precisao: BlocoPrecisao = BlocoPrecisao()
    temporal: BlocoTemporal = BlocoTemporal()
    escopo: BlocoEscopo = BlocoEscopo()
    x: BlocoX = BlocoX()
    extra: str = ""
    template_id: int | None = None
    valores_template: dict[str, str] = Field(default_factory=dict)


class ProblemaOut(BaseModel):
    codigo: str
    mensagem: str
    posicao: int | None = None


class ComposeResponse(BaseModel):
    query: str
    valida: bool
    erros: list[ProblemaOut]
    avisos: list[ProblemaOut]
    deeplinks: dict[str, str]
    compatibilidade: dict[str, list[str]]
    # Campos adicionais (contrato original preservado): X, TikTok, YouTube, Google Notícias.
    deeplinks_extra: dict[str, str] = Field(default_factory=dict)
    compatibilidade_extra: dict[str, list[str]] = Field(default_factory=dict)
    operadores_x: list[str] = Field(default_factory=list)


class ValidateRequest(BaseModel):
    query: str


class ValidateResponse(BaseModel):
    query: str
    valida: bool
    erros: list[ProblemaOut]
    avisos: list[ProblemaOut]
    operadores: dict[str, list[str]]
    deeplinks: dict[str, str]
    compatibilidade: dict[str, list[str]]
    deeplinks_extra: dict[str, str] = Field(default_factory=dict)
    compatibilidade_extra: dict[str, list[str]] = Field(default_factory=dict)
    operadores_x: list[str] = Field(default_factory=list)


class TemplateIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    categoria: str = "custom"
    descricao: str = ""
    query: str = Field(min_length=1)
    placeholders: list[str] = Field(default_factory=list)


class TemplateOut(BaseModel):
    id: int
    nome: str
    categoria: str
    descricao: str
    query: str
    placeholders: list[str]
    origem_pdf: bool
    criado_em: datetime


class HistoryIn(BaseModel):
    query: str = Field(min_length=1)
    motor: str = "google"
    origem: str = "builder"


class HistoryOut(BaseModel):
    id: int
    query: str
    motor: str
    origem: str
    criado_em: datetime
