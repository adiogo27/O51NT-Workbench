"""Agendador de monitores (APScheduler AsyncIOScheduler).

Fonte única da verdade: tabela `monitor`. Os jobs ficam em memória e são reconstruídos
no startup a partir dela (sem jobstore serializado — evita duas fontes divergentes).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text
from sqlmodel import Session, select

from app.db import get_engine
from app.models._base import agora
from app.models.monitor import Monitor, MonitorRun
from app.services import alerts, hashtag_tracker, query_compose, radar
from app.services.scraper import get_scraper

logger = logging.getLogger("o51nt.scheduler")

_scheduler: AsyncIOScheduler | None = None


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo("America/Sao_Paulo")
    except Exception:
        return ZoneInfo("UTC")


def validar_cron(expr: str) -> CronTrigger:
    """Levanta ValueError se a expressão crontab (5 campos) for inválida."""
    if len(expr.split()) != 5:
        raise ValueError("cron deve ter 5 campos: min hora dia mês dia_semana")
    return CronTrigger.from_crontab(expr, timezone=_tz())


def proxima_execucao(expr: str) -> datetime | None:
    trig = validar_cron(expr)
    nxt = trig.get_next_fire_time(None, datetime.now(_tz()))
    return nxt.astimezone(UTC) if nxt else None


def _job_id(monitor_id: int) -> str:
    return f"monitor-{monitor_id}"


async def executar_monitor(monitor_id: int) -> MonitorRun | None:
    """Executor padrão. Tipo 'query' → deeplinks + timeline. Tipo 'hashtag' → scraping ético."""
    with Session(get_engine()) as session:
        mon = session.get(Monitor, monitor_id)
        if mon is None:
            return None
        # motores originais + X/TikTok/YouTube/Google Notícias (chaves adicionais no mesmo dict)
        deeplinks = query_compose.deeplinks(mon.query) | query_compose.deeplinks_extra(mon.query)
        resultado: dict[str, Any] = {}
        status, log = "ok", ""
        try:
            if mon.tipo == "hashtag":
                resultado = await hashtag_tracker.coletar(session, get_scraper(), mon.query)
                erros = [f for f, v in resultado["fontes"].items() if "erro" in v]
                if erros and len(erros) == len(resultado["fontes"]):
                    status = "erro"
                log = f"hashtag {resultado['tag']}: {resultado['ocorrencias_alvo']} ocorrência(s)"
            else:
                log = "deeplinks gerados"
            # Radar: casa a query com os itens já em cache desde a última execução (ou últimos 7 dias)
            novos_hits = radar.casar_monitor_cache(session, mon, desde=mon.ultima_execucao)
            resultado["radar"] = {"novos_hits": len(novos_hits), "hits": [radar.hit_resumo(h) for h in novos_hits[:20]]}
            log += f" | radar: {len(novos_hits)} novo(s) hit(s)"
        except Exception as exc:
            status, log = "erro", f"{type(exc).__name__}: {exc}"
            logger.exception("falha ao executar monitor", extra={"dados": {"monitor_id": monitor_id}})

        evento = {
            "monitor_id": mon.id,
            "nome": mon.nome,
            "query": mon.query,
            "status": status,
            "executado_em": agora().isoformat(),
            "deeplinks": deeplinks,
            "resultado": resultado,
        }
        log += " | " + await alerts.disparar(mon.canal_alerta, evento, mon.webhook_url)

        run = MonitorRun(
            monitor_id=monitor_id,
            status=status,
            deeplinks_json=json.dumps(deeplinks, ensure_ascii=False),
            resultado_json=json.dumps(resultado, ensure_ascii=False, default=str),
            log=log,
        )
        mon.ultima_execucao = run.executado_em
        try:
            mon.proxima_execucao = proxima_execucao(mon.cron) if mon.ativo else None
        except ValueError:
            mon.proxima_execucao = None
        session.add(run)
        session.add(mon)
        session.commit()
        session.refresh(run)
        logger.info("monitor executado", extra={"dados": {"monitor_id": monitor_id, "status": status}})
        return run


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler


def agendar(mon: Monitor) -> None:
    if _scheduler is None or mon.id is None:
        return
    jid = _job_id(mon.id)
    if not mon.ativo:
        if _scheduler.get_job(jid):
            _scheduler.remove_job(jid)
        return
    _scheduler.add_job(
        executar_monitor,
        trigger=validar_cron(mon.cron),
        args=[mon.id],
        id=jid,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )


def desagendar(monitor_id: int) -> None:
    if _scheduler is not None and _scheduler.get_job(_job_id(monitor_id)):
        _scheduler.remove_job(_job_id(monitor_id))


RADAR_JOB_ID = "radar-ciclo"


async def executar_radar() -> None:
    from app.services.scraper import get_scraper as _scraper

    with Session(get_engine()) as session:
        try:
            await radar.ciclo(session, _scraper())
        except Exception:
            logger.exception("falha no ciclo do radar")


def job_radar():  # noqa: ANN201
    return _scheduler.get_job(RADAR_JOB_ID) if _scheduler is not None else None


def agendar_radar() -> None:
    """Lê as preferências (radarAtivo / radarIntervaloMin) e (re)agenda o ciclo periódico."""
    if _scheduler is None:
        return
    from app.routers.settings import carregar  # import tardio: evita ciclo routers ↔ services

    prefs = carregar().preferencias
    if not prefs.radarAtivo:
        if _scheduler.get_job(RADAR_JOB_ID):
            _scheduler.remove_job(RADAR_JOB_ID)
        return
    _scheduler.add_job(
        executar_radar,
        trigger=IntervalTrigger(minutes=prefs.radarIntervaloMin, timezone=_tz()),
        id=RADAR_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=600,
        next_run_time=datetime.now(_tz()) + timedelta(seconds=20),  # primeiro ciclo logo após subir
    )


def iniciar() -> AsyncIOScheduler:
    """Sobe o scheduler e reconstrói os jobs a partir da tabela Monitor."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = AsyncIOScheduler(timezone=_tz())
    _scheduler.start()
    with Session(get_engine()) as session:
        session.exec(text("DROP TABLE IF EXISTS apscheduler_jobs"))  # type: ignore[call-overload]  # legado v1.0
        session.commit()
        monitores = session.exec(select(Monitor)).all()
        for m in monitores:
            try:
                agendar(m)
            except ValueError:
                logger.warning("cron inválido ignorado", extra={"dados": {"monitor_id": m.id, "cron": m.cron}})
    agendar_radar()
    return _scheduler


def parar() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
