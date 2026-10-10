"""Pipeline de IA (OpenClaw): fila de tarefas, custo diário e auditoria das ferramentas OSINT externas.

Só entra na fila o que já casou deterministicamente com os termos dos monitores (MonitorHit) ou passou do limiar do
detector de convocações (Deteccao). Cada tarefa guarda a saída JSON de cada agent, o custo e o estado de aprovação.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.models._base import agora

STATUS = ("pendente", "em_processo", "concluida", "erro")
VEREDITOS = ("RELEVANTE", "OBSERVAR", "DESCARTAR")
APROVACOES = ("nao_se_aplica", "pendente", "aprovada", "rejeitada")


class IaTarefa(SQLModel, table=True):
    __tablename__ = "ia_tarefa"
    __table_args__ = (UniqueConstraint("origem", "url"),)

    id: int | None = Field(default=None, primary_key=True)
    origem: str = Field(index=True)  # hit | deteccao
    hit_id: int | None = Field(default=None, index=True)
    deteccao_id: int | None = Field(default=None, index=True)
    monitor_id: int | None = None
    monitor_nome: str = ""  # pode acumular vários monitores ("A; B") quando a mesma URL casa em mais de um
    monitor_query: str = ""
    url: str = Field(index=True)
    titulo: str = ""
    resumo: str = ""
    fonte_nome: str = ""
    termos: str = ""
    publicado_em: datetime | None = None
    texto_chars: int = 0  # tamanho do texto da matéria enviado ao LLM (0 = só título/resumo)

    status: str = Field(default="pendente", index=True)  # pendente | em_processo | concluida | erro
    etapa: str = ""  # última etapa executada: triagem | extracao | pesquisa | cartao | saidas
    tentativas: int = 0
    erro: str = ""

    veredito: str | None = Field(default=None, index=True)  # RELEVANTE | OBSERVAR | DESCARTAR
    severidade: str | None = None  # baixa | media | alta | critica
    justificativa: str = ""
    secao_sugerida: str | None = None
    eh_evento: bool = False
    triagem_json: str = "{}"
    evento_json: str = "{}"
    pesquisa_json: str = "{}"
    cartao_json: str = "{}"
    aterramento_json: str = "{}"  # checagem de aterramento (OOVS): afirmações do cartão × trechos das fontes
    verificacao_json: str = "{}"  # origens distintas, corroborações, etiqueta de confiança (determinístico)

    aprovacao: str = Field(default="nao_se_aplica", index=True)  # nao_se_aplica | pendente | aprovada | rejeitada
    aprovado_por: str = ""
    aprovado_em: datetime | None = None
    alerta_id: int | None = None
    boletim_item_id: int | None = None
    agenda_evento_id: int | None = None
    telegram_enviado: bool = False
    resumo_enviado: bool = False  # já saiu no resumo periódico (OBSERVAR)

    tokens_entrada: int = 0
    tokens_saida: int = 0
    custo_usd: float = 0.0
    modelos: str = ""  # modelos usados por etapa, ex.: "triagem=claude-haiku-5-5; cartao=claude-sonnet-5-5"

    criado_em: datetime = Field(default_factory=agora, index=True)
    iniciado_em: datetime | None = None
    concluido_em: datetime | None = None


class IaCusto(SQLModel, table=True):
    """Consumo agregado por dia (teto diário em preferências)."""

    __tablename__ = "ia_custo"

    id: int | None = Field(default=None, primary_key=True)
    data: date = Field(unique=True, index=True)
    chamadas: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0
    custo_usd: float = 0.0
    tarefas: int = 0


class FerramentaExecucao(SQLModel, table=True):
    """Auditoria das ferramentas OSINT executadas no servidor (quem, o quê, quando, resultado resumido)."""

    __tablename__ = "ferramenta_execucao"

    id: int | None = Field(default=None, primary_key=True)
    ferramenta: str = Field(index=True)
    alvo: str
    solicitante: str = ""
    ok: bool = True
    duracao_ms: int = 0
    resumo: str = ""  # primeiros caracteres da saída (ferramentas sensíveis: só a contagem de linhas)
    criado_em: datetime = Field(default_factory=agora, index=True)
