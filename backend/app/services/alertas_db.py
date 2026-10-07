"""Alertas persistidos (tabela `alerta`) + emissão pelos canais locais de `services.alerts` (JSONL/webhook)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.alerta import Alerta
from app.services import alerts


def alerta_para_evento(a: Alerta, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "tipo": a.tipo,
        "severidade": a.severidade,
        "titulo": a.titulo,
        "resumo": a.resumo,
        "url": a.url,
        "alerta_id": a.id,
        "deteccao_id": a.deteccao_id,
        "invite_id": a.invite_id,
        "monitor_id": a.monitor_id,
        "executado_em": a.criado_em.isoformat(),
    }
    if extra:
        ev.update(extra)
    return ev


async def registrar(session: Session, alerta: Alerta, canal: str = "jsonl", webhook_url: str | None = None, extra: dict[str, Any] | None = None) -> Alerta:
    """Grava o alerta e dispara o canal configurado. Nunca levanta por falha do canal."""
    session.add(alerta)
    session.commit()
    session.refresh(alerta)
    alerta.canal_log = await alerts.disparar(canal, alerta_para_evento(alerta, extra), webhook_url)
    session.add(alerta)
    session.commit()
    session.refresh(alerta)
    return alerta


def registrar_sync(session: Session, alerta: Alerta) -> Alerta:
    """Versão síncrona sem disparo de canal (quem chama já emitiu o JSONL — ex.: radar._alertar)."""
    session.add(alerta)
    session.commit()
    session.refresh(alerta)
    return alerta


def contagem_nao_lidos(session: Session) -> dict[str, int]:
    rows = session.exec(select(Alerta.tipo, func.count(Alerta.id)).where(Alerta.lido == False).group_by(Alerta.tipo)).all()  # noqa: E712
    por_tipo = {t: int(n) for t, n in rows}
    criticos = session.exec(select(func.count(Alerta.id)).where(Alerta.lido == False, Alerta.severidade == "critica")).one()  # noqa: E712
    return {"total": sum(por_tipo.values()), "criticos": int(criticos), **{k: por_tipo.get(k, 0) for k in ("convocacao", "convite", "radar")}}
