"""Combinação ponderada dos componentes → score 0-100 e severidade. Pesos de componentes ausentes são redistribuídos."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severidade = Literal["baixa", "media", "alta", "critica"]
SEVERIDADES: tuple[str, ...] = ("baixa", "media", "alta", "critica")


@dataclass(slots=True)
class Pesos:
    lexico: float = 0.45
    visual: float = 0.20
    referencia: float = 0.20
    monitor: float = 0.15
    bonus_distribuicao: int = 15


@dataclass(slots=True)
class Componentes:
    lexico: int = 0
    visual: int | None = None  # prob. "cartaz" × 100 (CLIP) — None sem perfil completo
    referencia: int | None = None  # similaridade com cartazes confirmados — None sem referências
    monitor: int = 0  # 100 se alguma query de monitor casou
    distribuicao: bool = False  # QR / convite de grupo presente
    detalhe: dict = field(default_factory=dict)


def combinar(c: Componentes, pesos: Pesos | None = None) -> tuple[int, dict]:
    """Retorna (score, decomposição). Componentes None não participam; seus pesos vão para os presentes."""
    p = pesos or Pesos()
    presentes: dict[str, tuple[int, float]] = {"lexico": (c.lexico, p.lexico), "monitor": (c.monitor, p.monitor)}
    if c.visual is not None:
        presentes["visual"] = (c.visual, p.visual)
    if c.referencia is not None:
        presentes["referencia"] = (c.referencia, p.referencia)
    soma_pesos = sum(w for _, w in presentes.values()) or 1.0
    total = 0.0
    decomposicao: dict = {"componentes": {}, "bonus_distribuicao": 0, "pesos_normalizados": True}
    for nome, (valor, w) in presentes.items():
        wn = w / soma_pesos
        parcela = valor * wn
        total += parcela
        decomposicao["componentes"][nome] = {"valor": valor, "peso": round(wn, 3), "parcela": round(parcela, 1)}
    if c.distribuicao:
        total += p.bonus_distribuicao
        decomposicao["bonus_distribuicao"] = p.bonus_distribuicao
    score = int(round(max(0.0, min(100.0, total))))
    decomposicao["score"] = score
    return score, decomposicao


def severidade(score: int, nao_pacifico: bool, lexico: int, limiar_alerta: int = 55, limiar_critico: int = 75) -> Severidade:
    """< 30 baixa · 30..alerta-1 média · alerta..crítico-1 alta · ≥ crítico crítica. Piso 'alta' se não pacífico com léxico forte."""
    if score >= limiar_critico:
        sev: Severidade = "critica"
    elif score >= limiar_alerta:
        sev = "alta"
    elif score >= 30:
        sev = "media"
    else:
        sev = "baixa"
    if nao_pacifico and lexico >= 50 and SEVERIDADES.index(sev) < SEVERIDADES.index("alta"):
        sev = "alta"
    return sev
