"""Cliente da instância LOCAL do SearXNG (metabusca), usada como fonte primária de busca.

Por que SearXNG: o Bing proíbe /search no robots.txt, então o scraper ético recusa consultá-lo
diretamente (o DuckDuckGo estava inacessível desta rede). O SearXNG local é operado pelo próprio usuário e consulta os
buscadores como um cliente de busca (uma consulta por pedido do operador), não como crawler.

Atenção (transparência): o SearXNG NÃO aplica o robots.txt dos buscadores upstream. O uso é
pessoal, de baixo volume, disparado manualmente/por monitor — ver README, seção "Scraping ético".
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("o51nt.searxng")

ENGINES_PADRAO: tuple[str, ...] = ("duckduckgo", "bing", "startpage")
ENGINES_IMAGENS: tuple[str, ...] = ("bing images", "duckduckgo images")  # categoria images (habilitar em data/searxng/settings.yml)


class SearxngIndisponivel(RuntimeError):
    pass


@dataclass(slots=True)
class ResultadoBusca:
    query: str
    url: str  # URL da consulta feita ao SearXNG (origem)
    status: int
    resultados: list[dict[str, Any]] = field(default_factory=list)
    engines_sem_resposta: list[Any] = field(default_factory=list)
    sha256: str = ""
    coletado_em: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    erro: str | None = None

    @property
    def ok(self) -> bool:
        return self.erro is None

    def texto_concatenado(self) -> str:
        """URL + título + snippet de cada resultado — insumo para os extratores (convites etc.)."""
        return "\n".join(f"{r.get('url', '')} {r.get('title', '')} {r.get('content', '')}" for r in self.resultados)


class SearxngClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 15.0,
        retries: int = 1,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        s = get_settings()
        self.base_url = (base_url or s.searxng_url).rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"User-Agent": s.user_agent, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def disponivel(self) -> bool:
        try:
            r = await self._client.get("/healthz", timeout=3.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def buscar(
        self, query: str, engines: list[str] | tuple[str, ...] = ENGINES_PADRAO, idioma: str = "pt-BR", pagina: int = 1, categorias: str | None = None
    ) -> ResultadoBusca:
        params = {
            "q": query,
            "format": "json",
            "engines": ",".join(engines),
            "language": idioma,
            "pageno": str(pagina),
            "safesearch": "0",
        }
        if categorias:
            params["categories"] = categorias
        origem = str(self._client.build_request("GET", "/search", params=params).url)
        ultimo_erro = ""
        for tentativa in range(self.retries + 1):
            try:
                r = await self._client.get("/search", params=params)
            except httpx.ConnectError as exc:
                raise SearxngIndisponivel(
                    f"SearXNG indisponível em {self.base_url} — suba com ./run.sh (Docker) ou defina O51NT_SEARXNG_URL"
                ) from exc
            except httpx.HTTPError as exc:
                ultimo_erro = f"{type(exc).__name__}: {exc}"
                continue
            if r.status_code == 403:
                return self._log(
                    ResultadoBusca(query, origem, 403, erro="SearXNG recusou formato JSON — habilite 'json' em search.formats")
                )
            if r.status_code >= 500 and tentativa < self.retries:
                ultimo_erro = f"HTTP {r.status_code}: " + " ".join(r.text.split())[:200]
                await asyncio.sleep(0.5)
                continue
            if r.status_code != 200:
                detalhe = " ".join(r.text.split())[:200]
                return self._log(
                    ResultadoBusca(query, origem, r.status_code, erro=f"HTTP {r.status_code}" + (f": {detalhe}" if detalhe else ""))
                )
            try:
                dados = r.json()
            except json.JSONDecodeError:
                return self._log(ResultadoBusca(query, origem, r.status_code, erro="resposta não-JSON"))
            resultados = [
                {
                    "titulo": x.get("title", ""),
                    "url": x.get("url", ""),
                    "content": x.get("content", ""),
                    "title": x.get("title", ""),
                    "engines": x.get("engines") or [x.get("engine")],
                    # categoria images: mantidos para o módulo Convocações
                    "img_src": x.get("img_src"),
                    "thumbnail_src": x.get("thumbnail_src"),
                    "publishedDate": x.get("publishedDate"),
                }
                for x in dados.get("results", [])
                if x.get("url")
            ]
            return self._log(
                ResultadoBusca(
                    query=query,
                    url=origem,
                    status=200,
                    resultados=resultados,
                    engines_sem_resposta=dados.get("unresponsive_engines", []),
                    sha256=hashlib.sha256(r.content).hexdigest(),
                )
            )
        return self._log(ResultadoBusca(query, origem, 0, erro=ultimo_erro or "falha"))

    @staticmethod
    def _log(res: ResultadoBusca) -> ResultadoBusca:
        dados: dict[str, Any] = {"query": res.query, "status": res.status, "n": len(res.resultados)}
        if res.sha256:
            dados["sha256"] = res.sha256
        if res.engines_sem_resposta:  # timeouts/CAPTCHA/429 dos buscadores, mesmo com HTTP 200
            dados["engines_sem_resposta"] = res.engines_sem_resposta
        if res.erro:  # chave só existe quando há erro
            dados["erro"] = res.erro
        nivel = logging.WARNING if (res.erro or res.engines_sem_resposta) else logging.INFO
        logger.log(nivel, "searxng", extra={"dados": dados})
        return res


_client: SearxngClient | None = None


def get_searxng() -> SearxngClient:
    global _client
    if _client is None:
        _client = SearxngClient()
    return _client


def set_searxng(c: SearxngClient | None) -> None:
    global _client
    _client = c


async def shutdown_searxng() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
