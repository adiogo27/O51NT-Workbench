"""Canais de alerta LOCAIS: arquivo JSONL em data/alerts/ e webhook HTTP genérico."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("o51nt.alerts")


def gravar_jsonl(evento: dict[str, Any]) -> str:
    s = get_settings()
    s.alerts_dir.mkdir(parents=True, exist_ok=True)
    arquivo = s.alerts_dir / f"{datetime.now(UTC):%Y-%m-%d}.jsonl"
    with arquivo.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")
    return str(arquivo)


async def enviar_webhook(url: str, evento: dict[str, Any]) -> int:
    async with httpx.AsyncClient(headers={"User-Agent": get_settings().user_agent}) as client:
        r = await client.post(url, json=evento, timeout=10.0)
        return r.status_code


async def disparar(canal: str, evento: dict[str, Any], webhook_url: str | None = None) -> str:
    """Retorna descrição do envio para a timeline. Nunca levanta exceção."""
    try:
        if canal == "jsonl":
            return f"jsonl: {gravar_jsonl(evento)}"
        if canal == "webhook":
            if not webhook_url:
                return "webhook: URL não configurada"
            status = await enviar_webhook(webhook_url, evento)
            return f"webhook: HTTP {status}"
        return "sem alerta"
    except Exception as exc:
        logger.warning("falha no alerta", extra={"dados": {"canal": canal, "erro": str(exc)}})
        return f"{canal}: falha ({exc})"
