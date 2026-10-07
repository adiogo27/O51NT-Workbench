from __future__ import annotations

from app.models.agenda import AgendaEvento
from app.models.alerta import Alerta
from app.models.backoff import DomainBackoff
from app.models.boletim import BoletimItem, Perfil
from app.models.convocacao import Deteccao, DeteccaoOcorrencia, FonteConvocacao, ReferenciaCartaz
from app.models.evidence import Evidence
from app.models.hashtag import Hashtag, HashtagSnapshot
from app.models.invite import Invite
from app.models.monitor import Monitor, MonitorRun
from app.models.query import QueryHistory
from app.models.radar import Fonte, FonteItem, MonitorHit
from app.models.template import QueryTemplate

__all__ = [
    "AgendaEvento",
    "Alerta",
    "BoletimItem",
    "Deteccao",
    "DeteccaoOcorrencia",
    "DomainBackoff",
    "Perfil",
    "Evidence",
    "Fonte",
    "FonteConvocacao",
    "FonteItem",
    "Hashtag",
    "HashtagSnapshot",
    "Invite",
    "Monitor",
    "MonitorHit",
    "MonitorRun",
    "QueryHistory",
    "QueryTemplate",
    "ReferenciaCartaz",
]
