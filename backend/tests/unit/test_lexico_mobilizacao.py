from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.services.convocacoes import lexico_mobilizacao as lx
from app.services.convocacoes.score import Componentes, Pesos, combinar, severidade

pytestmark = pytest.mark.unit
REF = datetime(2026, 10, 7, tzinfo=UTC)
CARTAZ = "GRITO DOS EXCLUÍDOS\nREVOLTA\nNAS RUAS\nDIA 11 DE OUTUBRO EM\nBELO HORIZONTE, MINAS GERAIS\nATO NÃO PACÍFICO"


def test_cartaz_exemplo_pontua_100_e_extrai_data_local() -> None:
    a = lx.avaliar(CARTAZ, REF)
    assert a.score == 100
    assert a.nao_pacifico and "ato nao pacifico" in a.termos["nao_pacifico"] and "revolta nas ruas" in a.termos["nao_pacifico"]
    assert a.data_evento == date(2026, 10, 11) and a.local == "Belo Horizonte/MG" and a.tempo == "futuro"
    assert a.cobertura == 4 and not a.noticiando


def test_ocr_sem_acentos_e_quebras_de_linha_tambem_casa() -> None:
    a = lx.avaliar("ATO NAO\nPACIFICO dia 11 de out em BH", REF)
    assert a.nao_pacifico and a.data_evento == date(2026, 10, 11) and a.local == "Belo Horizonte/MG"


def test_noticia_sobre_protesto_passado_e_rebaixada() -> None:
    n = "Manifestantes protestaram em Belo Horizonte no dia 11 de outubro; segundo a PM, três foram presos e o ato terminou às 18h."
    a = lx.avaliar(n, datetime(2026, 10, 12, tzinfo=UTC))
    assert a.noticiando and a.tempo == "passado" and a.score <= 30
    assert "segundo a pm" in a.pistas_noticiando and "data no passado" in a.pistas_noticiando


def test_texto_neutro_nao_pontua() -> None:
    assert lx.avaliar("foto do churrasco de domingo com a família", REF).score <= 10
    assert lx.avaliar("", REF).score == 0


def test_convocacao_com_distribuicao_hora_e_dia_semana() -> None:
    a = lx.avaliar("Vem pra rua sábado 11/10 às 14h na Praça Sete, BH! Compartilhe. Link do grupo: chat.whatsapp.com/abcDEF12345", REF)
    assert a.score == 100 and a.hora_evento == "14:00" and a.data_evento == date(2026, 10, 11)
    assert "distribuicao" in a.termos and "vem" in a.pistas_convocando and "hora explícita" in a.pistas_convocando


def test_extras_e_excluir() -> None:
    base = lx.avaliar("encontro do coletivo quinta", REF)
    com_extra = lx.avaliar("encontro do coletivo quinta", REF, extras=["encontro do coletivo"])
    assert com_extra.score > base.score and "encontro do coletivo" in com_extra.termos["convocacao"]
    sem = lx.avaliar("greve geral amanhã", REF, excluir=["greve geral", "greve"])
    assert "convocacao" not in sem.termos


def test_datas_numericas_e_ano_seguinte() -> None:
    d, h = lx.extrair_data("ato dia 03/01 as 9h", date(2026, 12, 20))
    assert d == date(2027, 1, 3) and h == "09:00"
    d2, _ = lx.extrair_data("manifestacao em 25 de dezembro de 2025", date(2026, 1, 5))
    assert d2 == date(2025, 12, 25)
    d3, h3 = lx.extrair_data("concentracao 14:30 hoje", date(2026, 10, 7))
    assert d3 is None and h3 == "14:30"
    assert lx.extrair_data("mulheres vivas 6x1 fim da escala", date(2026, 10, 7)) == (None, None)  # "ruas 6x1" não é hora
    assert lx.extrair_data("ato as 9 horas na praca", date(2026, 10, 7))[1] == "09:00"


def test_local_prioriza_cidade_e_apelidos() -> None:
    assert lx.extrair_local("ato em minas gerais e em belo horizonte") == "Belo Horizonte/MG"
    assert lx.extrair_local("vamos todos pra sampa") == "São Paulo/SP"
    assert lx.extrair_local("no rio de janeiro") == "Rio de Janeiro/RJ"
    assert lx.extrair_local("sem lugar") is None


def test_score_redistribui_pesos_e_bonus() -> None:
    s_leve, dec = combinar(Componentes(lexico=100, monitor=0), Pesos())
    assert s_leve == 75 and set(dec["componentes"]) == {"lexico", "monitor"}  # 0.45/(0.45+0.15) = 0.75
    s_full, _ = combinar(Componentes(lexico=100, visual=80, referencia=0, monitor=100), Pesos())
    assert s_full == 76  # 45 + 16 + 0 + 15
    s_bonus, dec2 = combinar(Componentes(lexico=100, monitor=0, distribuicao=True), Pesos())
    assert s_bonus == 90 and dec2["bonus_distribuicao"] == 15
    assert combinar(Componentes(lexico=0, monitor=0))[0] == 0


def test_severidade_limiares_e_piso_nao_pacifico() -> None:
    assert severidade(10, False, 10) == "baixa"
    assert severidade(40, False, 40) == "media"
    assert severidade(60, False, 60) == "alta"
    assert severidade(80, False, 80) == "critica"
    assert severidade(40, True, 60) == "alta"  # piso: não pacífico com léxico forte
    assert severidade(60, False, 60, limiar_alerta=70, limiar_critico=90) == "media"
