"""Cliente do gateway OpenClaw (endpoint compatível com OpenAI, só no loopback, token do gateway).

`POST /v1/chat/completions` com `model: "openclaw/<agent>"` executa um turno do agent com a persona, as skills e as
restrições de ferramentas dele. Cada requisição usa uma sessão nova (sem histórico acumulado). O cabeçalho
`x-openclaw-model` troca o modelo só naquela chamada (triagem barata). Nada aqui conhece as chaves das APIs de IA:
elas ficam no ambiente do OpenClaw.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("o51nt.ia")

# estimativa de custo (US$ por 1M tokens: entrada, saída) quando o gateway não informa; serve ao teto diário
PRECOS_ESTIMADOS: tuple[tuple[str, float, float], ...] = (
    ("haiku", 1.0, 5.0),
    ("sonnet", 3.0, 15.0),
    ("opus", 15.0, 75.0),
    ("fable", 15.0, 75.0),
    ("mythos", 15.0, 75.0),
    ("gpt", 2.0, 8.0),
)


class OpenClawIndisponivel(RuntimeError):
    """Gateway fora do ar / sem token / recusou a conexão — a tarefa volta para a fila."""


class OpenClawErro(RuntimeError):
    def __init__(self, status: int, detalhe: str) -> None:
        super().__init__(f"HTTP {status}: {detalhe[:300]}")
        self.status = status
        self.detalhe = detalhe


class RespostaInvalida(ValueError):
    """O agent não devolveu JSON válido no esquema pedido."""


@dataclass(slots=True)
class Resposta:
    texto: str
    modelo: str = ""
    tokens_entrada: int = 0
    tokens_saida: int = 0
    custo_usd: float = 0.0
    bruto: dict[str, Any] = field(default_factory=dict)


def estimar_custo(modelo: str, entrada: int, saida: int) -> float:
    m = (modelo or "").lower()
    for chave, pe, ps in PRECOS_ESTIMADOS:
        if chave in m:
            return round((entrada * pe + saida * ps) / 1_000_000, 6)
    return round((entrada * 3.0 + saida * 15.0) / 1_000_000, 6)


def extrair_json(texto: str) -> dict[str, Any]:
    """Aceita JSON puro, JSON em cerca ```json … ``` ou JSON cercado de prosa (primeiro objeto balanceado)."""
    if not texto or not texto.strip():
        raise RespostaInvalida("resposta vazia")
    t = texto.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    candidatos = [m.group(1)] if m else []
    candidatos.append(t)
    ini = t.find("{")
    if ini >= 0:
        prof = 0
        for i in range(ini, len(t)):
            if t[i] == "{":
                prof += 1
            elif t[i] == "}":
                prof -= 1
                if prof == 0:
                    candidatos.append(t[ini : i + 1])
                    break
    for c in candidatos:
        try:
            obj = json.loads(c)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    raise RespostaInvalida(f"sem JSON válido na resposta: {t[:160]!r}")


class ClienteOpenClaw:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        s = get_settings()
        self.base_url = (base_url or s.openclaw_url).rstrip("/")
        self.token = token if token is not None else s.openclaw_gateway_token
        self.timeout = timeout or s.openclaw_timeout_s
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, transport=transport, headers={"User-Agent": s.user_agent})

    @property
    def configurado(self) -> bool:
        return bool(self.token)

    async def disponivel(self) -> bool:
        try:
            r = await self._client.get("/health", timeout=5.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def perguntar(self, agent: str, mensagem: str, *, modelo: str | None = None, max_tokens: int = 800, sessao: str | None = None, timeout: float | None = None) -> Resposta:
        if not self.token:
            raise OpenClawIndisponivel("OPENCLAW_GATEWAY_TOKEN ausente no .env (05_openclaw.sh grava)")
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        if modelo:
            headers["x-openclaw-model"] = modelo
        if sessao:
            headers["x-openclaw-session-key"] = sessao
        corpo = {"model": f"openclaw/{agent}", "messages": [{"role": "user", "content": mensagem}], "max_completion_tokens": max_tokens, "stream": False}
        try:
            r = await self._client.post("/v1/chat/completions", json=corpo, headers=headers, timeout=timeout or self.timeout)
        except httpx.ConnectError as exc:
            raise OpenClawIndisponivel(f"gateway inacessível em {self.base_url}: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise OpenClawErro(504, f"tempo esgotado ({timeout or self.timeout:.0f}s) aguardando o agent {agent}") from exc
        if r.status_code in (401, 403):
            raise OpenClawIndisponivel(f"token do gateway recusado (HTTP {r.status_code})")
        if r.status_code != 200:
            raise OpenClawErro(r.status_code, r.text)
        dados = r.json()
        escolhas = dados.get("choices") or []
        texto = ""
        if escolhas:
            msg = escolhas[0].get("message") or {}
            conteudo = msg.get("content")
            texto = conteudo if isinstance(conteudo, str) else " ".join(str(p.get("text", "")) for p in (conteudo or []) if isinstance(p, dict))
        uso = dados.get("usage") or {}
        entrada = int(uso.get("prompt_tokens") or uso.get("input_tokens") or 0)
        saida = int(uso.get("completion_tokens") or uso.get("output_tokens") or 0)
        modelo_usado = str(dados.get("model") or modelo or "")
        custo = float(uso.get("cost_usd") or uso.get("costUsd") or 0) or estimar_custo(modelo_usado, entrada, saida)
        return Resposta(texto=texto, modelo=modelo_usado, tokens_entrada=entrada, tokens_saida=saida, custo_usd=custo, bruto=dados)

    async def close(self) -> None:
        await self._client.aclose()


_cliente: ClienteOpenClaw | None = None


def get_cliente() -> ClienteOpenClaw:
    global _cliente
    if _cliente is None:
        _cliente = ClienteOpenClaw()
    return _cliente


def set_cliente(c: ClienteOpenClaw | None) -> None:
    """Testes injetam um cliente com `httpx.MockTransport` (FakeOpenClaw)."""
    global _cliente
    _cliente = c


async def shutdown_cliente() -> None:
    global _cliente
    if _cliente is not None:
        await _cliente.close()
        _cliente = None
