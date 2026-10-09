from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlmodel import Session

from app import __version__, sdnotify
from app.config import get_settings
from app.db import get_engine, init_db
from app.logging_config import configure_logging
from app.middleware_auth import AuthMiddleware
from app.routers import agenda, alertas, auth, boletim, convocacoes, evidence, hashtags, images, invites, monitors, perfis, query_builder, radar, scraping, settings, tools
from app.seed import seed_fontes, seed_templates
from app.services import auth as auth_svc
from app.services import radar as radar_svc  # alias: `radar` já é o router importado acima
from app.services import retention, scheduler
from app.services.scraper import shutdown_scraper
from app.services.searxng_client import shutdown_searxng

logger = logging.getLogger("o51nt")
INICIADO_EM = datetime.now(UTC)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    s.ensure_dirs()
    configure_logging(s.logs_dir)
    init_db()
    with Session(get_engine()) as session:
        seed_templates(session)
        seed_fontes(session)
        radar_svc.sincronizar_fontes_hashtags(session)  # monitores de hashtag antigos ganham a fonte Mastodon
        retention.aplicar_politica(session)
        auth_svc.garantir_admin(session)  # login do painel (só com O51NT_ADMIN_EMAIL)
        auth_svc.limpar_expirados(session)
    if s.scheduler_enabled:
        scheduler.iniciar()
    logger.info("O51NT Workbench iniciado", extra={"dados": {"versao": __version__, "porta": s.port, "auth": s.auth_enabled}})
    sdnotify.notify("READY=1")  # systemd Type=notify (no-op fora do systemd)
    watchdog = sdnotify.iniciar_watchdog()
    yield
    sdnotify.notify("STOPPING=1")
    if watchdog is not None:
        watchdog.cancel()
    scheduler.parar()
    await shutdown_scraper()
    await shutdown_searxng()


def create_app() -> FastAPI:
    app = FastAPI(title="O51NT Workbench", version=__version__, lifespan=lifespan)
    app.add_middleware(AuthMiddleware)
    for r in (auth, query_builder, scraping, monitors, invites, tools, evidence, hashtags, images, settings, agenda, perfis, boletim, radar, convocacoes, alertas):
        app.include_router(r.router)

    @app.get("/api/health", tags=["system"])
    async def health() -> dict:
        db_ok = True
        try:
            with Session(get_engine()) as session:
                session.exec(text("SELECT 1"))  # type: ignore[call-overload]
        except Exception:
            db_ok = False
        return {
            "status": "ok" if db_ok else "degradado",
            "db": db_ok,
            "scheduler": scheduler.get_scheduler() is not None,
            "ml": _ml_resumo(),
            "uptime_s": int((datetime.now(UTC) - INICIADO_EM).total_seconds()),
        }

    @app.get("/api/version", tags=["system"])
    async def version() -> dict:
        return {"nome": "O51NT Workbench", "versao": __version__, "user_agent": get_settings().user_agent}

    _montar_frontend(app)
    return app


def _ml_resumo() -> dict:
    try:
        from app.services.convocacoes.analisador import get_analisador

        c = get_analisador().capacidades()
        return {"perfil": c["perfil"], "ocr": c["ocr_instalado"], "clip": c["clip_instalado"], "carregados": c["carregados"]}
    except Exception:  # nunca derruba o health
        return {"perfil": "indisponivel"}


def _montar_frontend(app: FastAPI) -> None:
    static = get_settings().static_dir
    index = static / "index.html"
    if (static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{caminho:path}", include_in_schema=False)
    async def spa(caminho: str) -> FileResponse:
        if caminho.startswith("api/"):
            raise HTTPException(404, "Rota de API não encontrada")
        alvo = (static / caminho).resolve()
        if caminho and alvo.is_file() and static.resolve() in alvo.parents:
            return FileResponse(alvo)
        if index.exists():
            return FileResponse(index)
        raise HTTPException(503, "Frontend não buildado. Rode: cd frontend && npm run build")


app = create_app()
