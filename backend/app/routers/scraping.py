"""Subaba "Scraping ético" do Query Builder (via SearXNG local) + status do scraper e localidades."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import locations, operators
from app.services.scraper import get_scraper
from app.services.searxng_client import SearxngIndisponivel, get_searxng

router = APIRouter(prefix="/api", tags=["scraping"])


class ScrapeQueryIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    engines: list[Literal["duckduckgo", "bing", "startpage"]] = ["duckduckgo", "bing", "startpage"]


@router.post("/query/scrape")
async def scrape_query(dados: ScrapeQueryIn) -> dict:
    val = operators.validar(dados.query)
    if not val.valida:
        return {"query": dados.query, "erro": "query inválida", "erros": [e.mensagem for e in val.erros], "execucoes": []}
    try:
        res = await get_searxng().buscar(dados.query, dados.engines)
    except SearxngIndisponivel as exc:
        raise HTTPException(503, str(exc)) from exc
    return {
        "query": dados.query,
        "execucoes": [
            {
                "fonte": "searxng:" + ",".join(dados.engines),
                "url": res.url,
                "status": res.status,
                "erro": res.erro,
                "sha256": res.sha256,
                "coletado_em": res.coletado_em,
                "resultados": [{"titulo": r["titulo"], "url": r["url"]} for r in res.resultados],
                "engines_sem_resposta": res.engines_sem_resposta,
            }
        ],
    }


@router.get("/searxng/status")
async def searxng_status() -> dict:
    c = get_searxng()
    return {"url": c.base_url, "disponivel": await c.disponivel()}


@router.get("/scraper/status")
async def status() -> dict:
    s = get_scraper()
    return {
        "user_agent": s.user_agent,
        "concorrencia": s.concorrencia,
        "timeout_s": s.timeout,
        "retries": s.retries,
        "dominios_em_backoff": s.backoff.listar(),
    }


@router.get("/locations")
async def localidades(q: str = "", uf: str | None = None, tipo: Literal["uf", "capital", "rodovia"] | None = None) -> list[dict]:
    return [{**loc, "termo": locations.termo_busca(loc)} for loc in locations.buscar(q, uf, tipo)]
