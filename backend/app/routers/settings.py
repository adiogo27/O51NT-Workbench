from __future__ import annotations

import json
import os
import re
import shutil
import tempfile

from fastapi import APIRouter
from pydantic import ValidationError, field_validator

from app.config import get_settings
from app.models.settings import AppSettings, Tema

router = APIRouter(prefix="/api/settings", tags=["settings"])

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
NAVEGADORES = ("firefox", "firefox-esr", "chromium", "google-chrome", "brave-browser", "microsoft-edge", "opera", "vivaldi")


class TemaValidado(Tema):
    @field_validator("primary", "secondary", "background", "foreground", "accent")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not _HEX.match(v):
            raise ValueError("cor deve estar no formato #RRGGBB")
        return v.lower()


class SettingsIn(AppSettings):
    tema: TemaValidado = TemaValidado()


def carregar() -> AppSettings:
    p = get_settings().settings_file
    if p.exists():
        try:
            return AppSettings.model_validate(json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, ValidationError):
            pass  # arquivo corrompido → defaults
    return AppSettings()


def salvar(cfg: AppSettings) -> None:
    p = get_settings().settings_file
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(cfg.model_dump(), fh, ensure_ascii=False, indent=2)
    os.replace(tmp, p)  # escrita atômica


@router.get("", response_model=AppSettings)
async def obter() -> AppSettings:
    return carregar()


@router.put("", response_model=AppSettings)
async def atualizar(dados: SettingsIn) -> AppSettings:
    cfg = AppSettings.model_validate(dados.model_dump())
    salvar(cfg)
    from app.services import scheduler  # import tardio: evita ciclo routers ↔ services

    scheduler.agendar_radar()
    scheduler.agendar_convocacoes()
    scheduler.agendar_convites()
    scheduler.agendar_ia()
    return cfg


@router.post("/reset", response_model=AppSettings)
async def resetar() -> AppSettings:
    cfg = AppSettings()
    salvar(cfg)
    from app.services import scheduler

    scheduler.agendar_radar()
    scheduler.agendar_convocacoes()
    scheduler.agendar_convites()
    scheduler.agendar_ia()
    return cfg


@router.get("/browsers")
async def navegadores() -> dict:
    return {"disponiveis": [b for b in NAVEGADORES if shutil.which(b)]}


# ------------------------------------------------------------------ Telegram (segredos só no .env; aqui só status)
def _mascarar(chat_id: str | None) -> str | None:
    if not chat_id:
        return None
    return chat_id if len(chat_id) <= 4 else f"{'*' * (len(chat_id) - 3)}{chat_id[-3:]}"


@router.get("/telegram")
async def telegram_status() -> dict:
    from app.services import alerts

    s = get_settings()
    info: dict = {"configurado": alerts.telegram_configurado(), "chat_id": _mascarar(s.telegram_chat_id), "bot": None, "erro": None}
    if s.telegram_bot_token:
        try:
            me = await alerts.telegram_get_me()
            info["bot"] = me.get("username") if me.get("ok") else None
            info["erro"] = None if me.get("ok") else me.get("erro")
        except Exception as exc:  # rede fora; não derruba a tela
            info["erro"] = f"sem acesso à API do Telegram: {exc}"
    else:
        info["erro"] = alerts.TELEGRAM_NAO_CONFIGURADO
    return info


@router.post("/telegram/teste")
async def telegram_teste() -> dict:
    """Envia uma mensagem de teste ao chat configurado."""
    from app.services import alerts

    if not alerts.telegram_configurado():
        return {"ok": False, "erro": alerts.TELEGRAM_NAO_CONFIGURADO}
    evento = {"tipo": "teste", "titulo": "Teste de alerta do O51NT Workbench", "resumo": "Se você leu isto, o canal Telegram está funcionando."}
    try:
        return await alerts.enviar_telegram(alerts.formatar_telegram(evento))
    except Exception as exc:
        return {"ok": False, "status": 0, "erro": str(exc)}

