"""Canais de alerta: arquivo JSONL em data/alerts/, webhook HTTP genérico e Telegram (bot próprio).

Todo evento é um dict livre (monitor, radar, convocação…); `formatar_telegram` extrai os campos
conhecidos e ignora o resto. Nenhum canal levanta exceção para quem chama (`disparar`).
"""

from __future__ import annotations

import html
import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("o51nt.alerts")

TELEGRAM_NAO_CONFIGURADO = "Telegram não configurado: defina TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env e reinicie"
TELEGRAM_MAX = 4000  # limite da API é 4096; margem para o rodapé
_EMOJI_SEVERIDADE = {"critica": "🚨", "alta": "🔴", "media": "🟠", "baixa": "🟡"}
_EMOJI_TIPO = {"radar": "📡", "convocacao": "📣", "convite": "🔗", "hashtag": "#️⃣", "agenda": "📅", "teste": "✅"}


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


# ------------------------------------------------------------------ Telegram
def telegram_configurado() -> bool:
    s = get_settings()
    return bool(s.telegram_bot_token and s.telegram_chat_id)


def _esc(v: Any) -> str:
    return html.escape(str(v), quote=False)


def _link(url: str, texto: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{_esc(texto)}</a>'


def formatar_telegram(evento: dict[str, Any]) -> str:
    """Mensagem HTML (parse_mode=HTML) a partir dos campos conhecidos do evento."""
    tipo = str(evento.get("tipo") or ("radar" if "hits" in evento else "monitor"))
    severidade = str(evento.get("severidade") or "")
    emoji = _EMOJI_SEVERIDADE.get(severidade) or _EMOJI_TIPO.get(tipo, "🔔")
    titulo = evento.get("titulo") or evento.get("nome") or tipo
    linhas = [f"{emoji} <b>O51NT</b> · {_esc(tipo)}{(' · ' + _esc(severidade)) if severidade else ''}", f"<b>{_esc(titulo)}</b>"]
    if evento.get("query"):
        linhas.append(f"<code>{_esc(str(evento['query'])[:300])}</code>")
    if evento.get("resumo"):
        linhas.append(_esc(str(evento["resumo"])[:400]))
    if evento.get("url"):
        linhas.append(_link(str(evento["url"]), str(evento["url"])[:120]))
    hits = evento.get("hits") or []
    if evento.get("novos_hits") is not None:
        linhas.append(f"{_esc(evento['novos_hits'])} novo(s) hit(s)")
    for h in hits[:5]:
        if not isinstance(h, dict):
            continue
        rotulo = str(h.get("titulo") or h.get("url") or "")[:100]
        fonte = f" — {_esc(h['fonte'])}" if h.get("fonte") else ""
        linhas.append(f"• {_link(str(h['url']), rotulo) if h.get('url') else _esc(rotulo)}{fonte}")
    if len(hits) > 5:
        linhas.append(f"… e mais {len(hits) - 5}")
    deeplinks = evento.get("deeplinks") or {}
    if not hits and isinstance(deeplinks, dict) and deeplinks.get("google"):
        linhas.append(_link(str(deeplinks["google"]), "abrir no Google") + (f" · {_link(str(deeplinks['x']), 'X')}" if deeplinks.get("x") else ""))
    quando = evento.get("executado_em") or datetime.now(UTC).isoformat()
    linhas.append(f"<i>{_esc(str(quando)[:19].replace('T', ' '))}</i>")
    texto = "\n".join(linhas)
    return texto if len(texto) <= TELEGRAM_MAX else texto[: TELEGRAM_MAX - 1] + "…"


async def enviar_telegram(texto: str, chat_id: str | None = None) -> dict[str, Any]:
    """Envia pela Bot API. Retorna {"ok", "message_id" | "erro", "status"}. Levanta httpx.HTTPError em falha de rede."""
    s = get_settings()
    if not s.telegram_bot_token or not (chat_id or s.telegram_chat_id):
        return {"ok": False, "status": 0, "erro": TELEGRAM_NAO_CONFIGURADO}
    url = f"{s.telegram_api_base}/bot{s.telegram_bot_token}/sendMessage"
    payload = {"chat_id": chat_id or s.telegram_chat_id, "text": texto, "parse_mode": "HTML", "disable_web_page_preview": True}
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, timeout=15.0)
    try:
        corpo = r.json()
    except ValueError:
        corpo = {}
    if r.status_code == 200 and corpo.get("ok"):
        return {"ok": True, "status": 200, "message_id": (corpo.get("result") or {}).get("message_id")}
    return {"ok": False, "status": r.status_code, "erro": str(corpo.get("description") or f"HTTP {r.status_code}")}


async def telegram_get_me() -> dict[str, Any]:
    """Identidade do bot (username) — usado na tela de configurações. Não expõe o token."""
    s = get_settings()
    if not s.telegram_bot_token:
        return {"ok": False, "erro": TELEGRAM_NAO_CONFIGURADO}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{s.telegram_api_base}/bot{s.telegram_bot_token}/getMe", timeout=10.0)
    corpo = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code == 200 and corpo.get("ok"):
        res = corpo.get("result") or {}
        return {"ok": True, "username": res.get("username"), "nome": res.get("first_name")}
    return {"ok": False, "erro": str(corpo.get("description") or f"HTTP {r.status_code}")}


# ------------------------------------------------------------------ despacho
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
        if canal == "telegram":
            gravar_jsonl(evento)  # o JSONL continua sendo o registro local; o Telegram é o aviso
            res = await enviar_telegram(formatar_telegram(evento))
            return f"telegram: enviado (msg {res['message_id']})" if res["ok"] else f"telegram: falha ({res['erro']})"
        return "sem alerta"
    except Exception as exc:
        logger.warning("falha no alerta", extra={"dados": {"canal": canal, "erro": str(exc)}})
        return f"{canal}: falha ({exc})"
