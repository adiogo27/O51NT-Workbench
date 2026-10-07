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
    return cfg


@router.post("/reset", response_model=AppSettings)
async def resetar() -> AppSettings:
    cfg = AppSettings()
    salvar(cfg)
    from app.services import scheduler

    scheduler.agendar_radar()
    scheduler.agendar_convocacoes()
    scheduler.agendar_convites()
    return cfg


@router.get("/browsers")
async def navegadores() -> dict:
    return {"disponiveis": [b for b in NAVEGADORES if shutil.which(b)]}

