"""Retenção do histórico de queries (por idade e/ou teto de entradas)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlmodel import Session, col, select

from app.models.query import QueryHistory


def podar_historico(session: Session, older_than_days: int | None = None, max_entries: int | None = None) -> int:
    """Remove entradas mais antigas que N dias e/ou além das N mais recentes. Retorna quantas removeu."""
    removidas = 0
    if older_than_days:
        limite = datetime.now(UTC) - timedelta(days=older_than_days)
        r = session.exec(delete(QueryHistory).where(col(QueryHistory.criado_em) < limite))  # type: ignore[call-overload]
        removidas += r.rowcount or 0
    if max_entries:
        corte = session.exec(
            select(QueryHistory.id)
            .order_by(col(QueryHistory.criado_em).desc(), col(QueryHistory.id).desc())
            .offset(max_entries)
            .limit(1)
        ).first()
        if corte is not None:
            manter = select(QueryHistory.id).order_by(col(QueryHistory.criado_em).desc(), col(QueryHistory.id).desc()).limit(max_entries)
            r = session.exec(delete(QueryHistory).where(col(QueryHistory.id).not_in(manter)))  # type: ignore[call-overload]
            removidas += r.rowcount or 0
    session.commit()
    return removidas


def aplicar_politica(session: Session) -> int:
    """Aplica a política configurada em data/settings.json (preferencias.historico*)."""
    from app.routers.settings import carregar

    p = carregar().preferencias
    return podar_historico(session, p.historicoRetencaoDias or None, p.historicoMaxEntradas or None)
