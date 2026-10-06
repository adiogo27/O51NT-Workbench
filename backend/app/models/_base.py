from __future__ import annotations

from datetime import UTC, datetime


def agora() -> datetime:
    return datetime.now(UTC)
