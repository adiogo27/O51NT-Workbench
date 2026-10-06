"""Agenda dos candidatos: queries de monitoramento (cruzando com a base DNIT), ICS e CSV."""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from app.models.agenda import AgendaEvento
from app.services import locations
from app.services.query_compose import citar, grupo_or

_RODOVIA_RE = re.compile(r"^\s*BR\s*-?\s*(\d{3})\s*$", re.IGNORECASE)

TIPOS: tuple[str, ...] = ("caminhada", "carreata", "motociata", "comicio", "ato", "debate", "entrevista", "reuniao", "outro")
TIPOS_COM_DESLOCAMENTO: frozenset[str] = frozenset({"carreata", "motociata", "caminhada", "comicio", "ato"})

# Termos de busca por tipo de evento (sinônimos usados em redes e imprensa).
TERMOS_POR_TIPO: dict[str, list[str]] = {
    "caminhada": ["caminhada", "ato"],
    "carreata": ["carreata", "comboio", "buzinaço"],
    "motociata": ["motociata", "motocarreata", "moto carreata"],
    "comicio": ["comício", "ato"],
    "ato": ["ato", "manifestação"],
    "debate": ["debate"],
    "entrevista": ["entrevista", "podcast"],
    "reuniao": ["reunião", "encontro"],
    "outro": [],
}
TERMOS_IMPACTO_RODOVIA: list[str] = ["bloqueio", "interdição", "trânsito", "congestionamento"]
DIAS_SEMANA = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def normalizar_rodovia(valor: str) -> str | None:
    """'br 116', 'BR116', 'BR-116' → 'BR-116'; outra coisa → None."""
    m = _RODOVIA_RE.match(valor or "")
    return f"BR-{m.group(1)}" if m else None


def rodovias_lista(ev: AgendaEvento) -> list[str]:
    return [r for r in ev.rodovias.split(",") if r]


def termos_rodovia(rodovias: list[str]) -> list[str]:
    """Reaproveita a base DNIT: BR-116 → (BR-116 OR "BR 116" OR BR116)."""
    return [locations.termo_busca({"tipo": "rodovia", "nome": r}) for r in rodovias]


def dia_semana(d: date) -> str:
    return DIAS_SEMANA[d.weekday()]


def montar_query(ev: AgendaEvento, motor: Literal["google", "x"] = "google") -> str:
    """Query de monitoramento do evento.

    candidato + (cidade OR rodovias) + (termos do tipo [+ impacto em rodovia]) + janela temporal.
    Google: after:(véspera). X: since:(véspera) -is:retweet.
    """
    partes: list[str] = [citar(ev.candidato)]
    locais: list[str] = []
    if ev.cidade.strip():
        locais.append(citar(ev.cidade))
    locais += termos_rodovia(rodovias_lista(ev))
    if len(locais) == 1:
        partes.append(locais[0])
    elif locais:
        partes.append("(" + " OR ".join(locais) + ")")
    termos = list(TERMOS_POR_TIPO.get(ev.tipo, []))
    if ev.impacto_rodovia:
        termos += [t for t in TERMOS_IMPACTO_RODOVIA if t not in termos]
    if termos:
        partes.append(grupo_or(termos))
    vespera = (ev.data - timedelta(days=1)).isoformat()
    if motor == "x":
        partes += ["-is:retweet", f"since:{vespera}"]
    else:
        partes.append(f"after:{vespera}")
    return " ".join(partes)


# ------------------------------------------------------------------ ICS (RFC 5545)
def _ics_escape(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _ics_fold(linha: str) -> str:
    """Dobra em 75 octetos (UTF-8) sem partir caractere multibyte; continuação começa com espaço."""
    dados = linha.encode("utf-8")
    if len(dados) <= 75:
        return linha
    partes: list[str] = []
    limite = 75
    while dados:
        corte = min(limite, len(dados))
        while corte > 0 and (dados[corte - 1] & 0xC0) == 0x80 and corte < len(dados):  # não partir multibyte
            corte -= 1
        while corte < len(dados) and (dados[corte] & 0xC0) == 0x80:
            corte -= 1
        partes.append(dados[:corte].decode("utf-8"))
        dados = dados[corte:]
        limite = 74  # as linhas seguintes levam o espaço de continuação
    return "\r\n ".join(partes)


_STATUS_ICS = {"previsto": "TENTATIVE", "confirmado": "CONFIRMED", "realizado": "CONFIRMED", "cancelado": "CANCELLED"}


def _dt_ics(d: date, hora: str | None) -> str:
    if hora:
        return f"TZID=America/Sao_Paulo:{d:%Y%m%d}T{hora.replace(':', '')}00"
    return f"VALUE=DATE:{d:%Y%m%d}"


def gerar_ics(eventos: list[AgendaEvento]) -> str:
    agora = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    linhas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//O51NT Workbench//Agenda//PT-BR", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for ev in eventos:
        inicio = f"DTSTART;{_dt_ics(ev.data, ev.hora_inicio)}"
        if ev.hora_inicio:
            fim_hora = ev.hora_fim
            if not fim_hora:  # sem fim informado: +1 h (sem passar da meia-noite)
                h, m = (int(x) for x in ev.hora_inicio.split(":"))
                fim_hora = f"{min(h + 1, 23):02d}:{m:02d}"
            fim = f"DTEND;{_dt_ics(ev.data, fim_hora)}"
        else:
            fim = f"DTEND;{_dt_ics(ev.data + timedelta(days=1), None)}"
        local = ", ".join(x for x in (ev.local, "/".join(x for x in (ev.cidade, ev.uf) if x)) if x)
        descricao = " | ".join(
            x
            for x in (
                f"Tipo: {ev.tipo}",
                f"Partido: {ev.partido}" if ev.partido else "",
                f"Rodovias: {', '.join(rodovias_lista(ev))}" if ev.rodovias else "",
                "IMPACTO EM RODOVIA FEDERAL" if ev.impacto_rodovia else "",
                f"Status: {ev.status}",
                ev.descricao,
            )
            if x
        )
        linhas += [
            "BEGIN:VEVENT",
            f"UID:o51nt-agenda-{ev.id}@local",
            f"DTSTAMP:{agora}",
            inicio,
            fim,
            f"SUMMARY:{_ics_escape(f'{ev.candidato} — {ev.titulo}')}",
            f"LOCATION:{_ics_escape(local)}",
            f"DESCRIPTION:{_ics_escape(descricao)}",
            f"STATUS:{_STATUS_ICS.get(ev.status, 'TENTATIVE')}",
            f"CATEGORIES:O51NT,{ev.tipo}",
        ]
        if ev.fonte_url:
            linhas.append(f"URL:{ev.fonte_url}")
        linhas.append("END:VEVENT")
    linhas.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(l) for l in linhas) + "\r\n"


CAMPOS_CSV = [
    "id", "data", "dia_semana", "hora_inicio", "hora_fim", "candidato", "partido", "cargo", "titulo", "tipo",
    "cidade", "uf", "local", "rodovias", "impacto_rodovia", "status", "fonte_url", "descricao", "monitor_id",
]


def gerar_csv(eventos: list[AgendaEvento]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CAMPOS_CSV)
    w.writeheader()
    for ev in eventos:
        w.writerow(
            {
                "id": ev.id,
                "data": ev.data.isoformat(),
                "dia_semana": dia_semana(ev.data),
                "hora_inicio": ev.hora_inicio or "",
                "hora_fim": ev.hora_fim or "",
                "candidato": ev.candidato,
                "partido": ev.partido,
                "cargo": ev.cargo,
                "titulo": ev.titulo,
                "tipo": ev.tipo,
                "cidade": ev.cidade,
                "uf": ev.uf,
                "local": ev.local,
                "rodovias": " ".join(rodovias_lista(ev)),
                "impacto_rodovia": "sim" if ev.impacto_rodovia else "não",
                "status": ev.status,
                "fonte_url": ev.fonte_url or "",
                "descricao": ev.descricao,
                "monitor_id": ev.monitor_id or "",
            }
        )
    return buf.getvalue()
