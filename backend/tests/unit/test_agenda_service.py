from __future__ import annotations

from datetime import date

import pytest

from app.models.agenda import AgendaEvento
from app.services import agenda as svc
from app.services.operators import validar

pytestmark = pytest.mark.unit


def evento(**kw) -> AgendaEvento:  # noqa: ANN003
    base = dict(
        id=7,
        candidato="Candidato A",
        titulo="Carreata de encerramento",
        tipo="carreata",
        data=date(2026, 10, 3),
        hora_inicio="14:30",
        cidade="Americana",
        uf="SP",
        rodovias="BR-116",
        impacto_rodovia=True,
    )
    base.update(kw)
    return AgendaEvento(**base)


@pytest.mark.parametrize(("entrada", "esperado"), [("BR-116", "BR-116"), ("br 116", "BR-116"), ("BR116", "BR-116"), (" br-040 ", "BR-040"), ("BR-16", None), ("Rodovia 116", None), ("", None)])
def test_normalizar_rodovia(entrada: str, esperado: str | None) -> None:
    assert svc.normalizar_rodovia(entrada) == esperado


def test_montar_query_google_cruza_cidade_rodovia_tipo_e_data() -> None:
    q = svc.montar_query(evento())
    # citar(): aspas só em termos com espaço (mesma convenção do Query Builder)
    assert q == (
        '"Candidato A" (Americana OR (BR-116 OR "BR 116" OR BR116)) '
        "(carreata OR comboio OR buzinaço OR bloqueio OR interdição OR trânsito OR congestionamento) after:2026-10-02"
    )
    assert validar(q).valida


def test_montar_query_x_usa_since_e_sem_retweet() -> None:
    q = svc.montar_query(evento(), "x")
    assert q.endswith("-is:retweet since:2026-10-02")
    assert "after:" not in q
    assert validar(q).valida


def test_montar_query_sem_local_e_tipo_outro() -> None:
    q = svc.montar_query(evento(cidade="", rodovias="", tipo="outro", impacto_rodovia=False))
    assert q == '"Candidato A" after:2026-10-02'


def test_montar_query_duas_rodovias() -> None:
    q = svc.montar_query(evento(cidade="", rodovias="BR-116,BR-040"))
    assert '((BR-116 OR "BR 116" OR BR116) OR (BR-040 OR "BR 040" OR BR040))' in q


def test_gerar_ics_estrutura_e_escape() -> None:
    ics = svc.gerar_ics([evento(local="Praça Central; portão 2, lado B", hora_fim=None), evento(id=8, hora_inicio=None, status="cancelado")])
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == 2
    assert "UID:o51nt-agenda-7@local" in ics
    assert "DTSTART;TZID=America/Sao_Paulo:20261003T143000" in ics
    assert "DTEND;TZID=America/Sao_Paulo:20261003T153000" in ics  # +1 h quando não há hora_fim
    assert "DTSTART;VALUE=DATE:20261003" in ics and "DTEND;VALUE=DATE:20261004" in ics  # dia inteiro
    assert "STATUS:CANCELLED" in ics and "STATUS:TENTATIVE" in ics
    assert "LOCATION:Praça Central\\; portão 2\\, lado B\\, Americana/SP" in ics
    assert "IMPACTO EM RODOVIA FEDERAL" in ics


def test_gerar_ics_dobra_linhas_longas_sem_partir_utf8() -> None:
    ics = svc.gerar_ics([evento(descricao="ç" * 200)])
    for linha in ics.split("\r\n"):
        assert len(linha.encode("utf-8")) <= 75
    # desdobrando (remove CRLF+espaço) a descrição volta inteira
    assert "ç" * 200 in ics.replace("\r\n ", "")


def test_gerar_csv() -> None:
    csv_txt = svc.gerar_csv([evento()])
    linhas = csv_txt.splitlines()
    assert linhas[0].startswith("id,data,dia_semana,hora_inicio")
    assert "Candidato A" in linhas[1] and "sábado" in linhas[1] and "BR-116" in linhas[1] and "sim" in linhas[1]


def test_dia_semana() -> None:
    assert svc.dia_semana(date(2026, 10, 4)) == "domingo"
