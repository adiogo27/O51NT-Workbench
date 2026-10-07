"""Analisador: orquestra imagem → QR → OCR → léxico → monitores → CLIP → score, fora do event-loop.

Singleton com carga preguiçosa dos modelos (OCR/CLIP), `asyncio.to_thread` + Semaphore(1) (uvicorn nunca bloqueia; RAM manda),
e descarga por ociosidade. Não toca no banco: recebe monitores já compilados e referências em cache; quem persiste é `coleta`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import resource
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.config import get_settings
from app.models.settings import Preferencias
from app.services import radar
from app.services.convocacoes import clip as clip_mod
from app.services.convocacoes import imagem as img_mod
from app.services.convocacoes import lexico_mobilizacao as lexico
from app.services.convocacoes import ocr as ocr_mod
from app.services.convocacoes.score import Componentes, Pesos, combinar, severidade

logger = logging.getLogger("o51nt.convocacoes")

LIMIAR_PHASH_IGUAL = 6  # Hamming ≤ 6 → mesma imagem (recorte/recompressão)
COSSENO_ZERO, COSSENO_CEM = 0.75, 0.92


@dataclass(slots=True)
class Entrada:
    imagem: bytes | None = None
    texto_post: str = ""
    post_url: str = ""
    imagem_url: str = ""
    plataforma: str = "desconhecida"
    publicado_em: datetime | None = None
    autor: str = ""
    host_imprensa: bool = False


@dataclass(slots=True)
class MonitorCompilado:
    id: int
    nome: str
    matcher: radar.Matcher


@dataclass(slots=True)
class RefCache:
    id: int
    phash: str
    embedding: np.ndarray | None = None
    rotulo: str = ""


@dataclass(slots=True)
class Analise:
    imagem: img_mod.ImagemNormalizada | None
    ocr: ocr_mod.ResultadoOCR | None
    qr: list[str]
    convites: list[tuple[str, str]]
    lexico: lexico.AvaliacaoLexico
    visual: dict[str, float] | None
    embedding: np.ndarray | None
    referencia: tuple[int | None, int, str] | None  # (referencia_id, score 0-100, motivo)
    termos_monitor: list[tuple[int, str, list[str]]]  # (monitor_id, nome, termos)
    componentes: Componentes
    score: int
    decomposicao: dict
    severidade: str
    ms: int
    capacidades: dict[str, Any] = field(default_factory=dict)

    @property
    def texto_ocr(self) -> str:
        return self.ocr.texto if self.ocr else ""


def pesos_de(prefs: Preferencias) -> Pesos:
    return Pesos(
        lexico=prefs.convocacoesPesoLexico,
        visual=prefs.convocacoesPesoVisual,
        referencia=prefs.convocacoesPesoReferencia,
        monitor=prefs.convocacoesPesoMonitor,
        bonus_distribuicao=prefs.convocacoesBonusDistribuicao,
    )


def _rss_mb() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)


class Analisador:
    def __init__(self, prefs_provider: Callable[[], Preferencias] | None = None, dir_modelos: Path | None = None) -> None:
        self._prefs_provider = prefs_provider
        self._dir_modelos = dir_modelos
        self._ocr: ocr_mod.MotorOCR | None = None
        self._clip: clip_mod.MotorCLIP | None = None
        self._lock = threading.Lock()
        self._sem: asyncio.Semaphore | None = None
        self.ultimo_uso: float | None = None
        self.analises = 0
        self.threads = max(1, min(4, (os.cpu_count() or 4) // 3))

    # ------------------------------------------------------------ infra
    def _prefs(self) -> Preferencias:
        if self._prefs_provider is not None:
            return self._prefs_provider()
        from app.routers.settings import carregar  # import tardio: evita ciclo routers ↔ services

        return carregar().preferencias

    def _modelos(self) -> Path:
        return self._dir_modelos or get_settings().models_dir

    def _semaforo(self) -> asyncio.Semaphore:
        if self._sem is None:
            self._sem = asyncio.Semaphore(1)
        return self._sem

    def _carregar_ocr(self) -> ocr_mod.MotorOCR | None:
        if self._ocr is None and ocr_mod.disponivel():
            with self._lock:
                if self._ocr is None:
                    t0 = time.monotonic()
                    self._ocr = ocr_mod.MotorOCR(self._modelos() / "rapidocr", threads=self.threads)
                    logger.info("OCR carregado", extra={"dados": {"modelo": self._ocr.modelo, "s": round(time.monotonic() - t0, 1)}})
        return self._ocr

    def _carregar_clip(self, prefs: Preferencias) -> clip_mod.MotorCLIP | None:
        if prefs.convocacoesPerfilML != "completo" or not clip_mod.disponivel():
            return None
        if self._clip is None:
            with self._lock:
                if self._clip is None:
                    t0 = time.monotonic()
                    self._clip = clip_mod.MotorCLIP(self._modelos(), threads=self.threads)
                    logger.info("CLIP carregado", extra={"dados": {"modelo": self._clip.nome, "s": round(time.monotonic() - t0, 1)}})
        return self._clip

    def capacidades(self) -> dict[str, Any]:
        prefs = self._prefs()
        return {
            "perfil": prefs.convocacoesPerfilML,
            "ocr_instalado": ocr_mod.disponivel(),
            "clip_instalado": clip_mod.disponivel(),
            "qr": True,
            "lexico": True,
            "carregados": [n for n, m in (("ocr", self._ocr), ("clip", self._clip)) if m is not None],
            "ocr_modelo": self._ocr.modelo if self._ocr else None,
            "clip_modelo": self._clip.nome if self._clip else None,
            "ultimo_uso": datetime.fromtimestamp(self.ultimo_uso, UTC).isoformat() if self.ultimo_uso else None,
            "analises": self.analises,
            "rss_mb": _rss_mb(),
            "threads": self.threads,
            "dir_modelos": str(self._modelos()),
        }

    def descarregar(self, forcar: bool = False) -> list[str]:
        """Libera modelos ociosos há mais de `convocacoesDescarregarMin` (ou todos, se `forcar`)."""
        prefs = self._prefs()
        ocioso = self.ultimo_uso is None or (time.monotonic() - self.ultimo_uso) > prefs.convocacoesDescarregarMin * 60
        if not (forcar or ocioso):
            return []
        liberados: list[str] = []
        with self._lock:
            if self._ocr is not None:
                self._ocr = None
                liberados.append("ocr")
            if self._clip is not None:
                self._clip = None
                liberados.append("clip")
        if liberados:
            import gc

            gc.collect()
            logger.info("modelos descarregados", extra={"dados": {"liberados": liberados, "rss_mb": _rss_mb()}})
        return liberados

    # ------------------------------------------------------------ análise
    async def analisar(self, entrada: Entrada, referencias: list[RefCache] | None = None, monitores: list[MonitorCompilado] | None = None) -> Analise:
        prefs = self._prefs()
        async with self._semaforo():
            return await asyncio.to_thread(self._analisar_sync, entrada, referencias or [], monitores or [], prefs)

    def _analisar_sync(self, entrada: Entrada, referencias: list[RefCache], monitores: list[MonitorCompilado], prefs: Preferencias) -> Analise:
        from app.services.convites import extrair_convites

        t0 = time.monotonic()
        self.ultimo_uso = time.monotonic()
        self.analises += 1
        imagem: img_mod.ImagemNormalizada | None = None
        res_ocr: ocr_mod.ResultadoOCR | None = None
        qr: list[str] = []
        visual: dict[str, float] | None = None
        embedding: np.ndarray | None = None

        if entrada.imagem:
            imagem = img_mod.abrir(entrada.imagem)  # ValueError sobe para o chamador (422)
            try:
                qr = img_mod.ler_qr(imagem)
            except Exception as exc:
                logger.warning("falha ao ler QR", extra={"dados": {"erro": str(exc)}})
            motor = self._carregar_ocr()
            if motor is not None:
                res_ocr = motor.ler(img_mod.preprocessar_para_ocr(imagem))
            clip_motor = self._carregar_clip(prefs)
            if clip_motor is not None:
                try:
                    embedding = clip_motor.embutir(imagem.pil)
                    visual = clip_motor.classificar(embedding)
                except Exception as exc:
                    logger.warning("falha no CLIP", extra={"dados": {"erro": str(exc)}})

        texto_ocr = res_ocr.texto if res_ocr else ""
        texto_total = "\n".join(p for p in (entrada.texto_post, texto_ocr, " ".join(qr)) if p)
        convites = extrair_convites(texto_total)
        ref_tempo = lexico.janela_referencia(entrada.publicado_em)
        av = lexico.avaliar(
            texto_total,
            referencia=ref_tempo,
            extras=prefs.convocacoesTermosExtra,
            excluir=prefs.convocacoesTermosExcluir,
            host_imprensa=entrada.host_imprensa,
        )

        # monitores (sintaxe do Query Builder) sobre texto do post + OCR
        termos_monitor: list[tuple[int, str, list[str]]] = []
        if monitores and texto_total.strip():
            alvo = radar.alvo_de(entrada.texto_post[:300], texto_total, entrada.post_url or entrada.imagem_url or "https://local/", entrada.publicado_em)
            for mc in monitores:
                termos = mc.matcher.casar(alvo)
                if termos:
                    termos_monitor.append((mc.id, mc.nome, termos))

        # referência (galeria de cartazes confirmados): pHash primeiro, cosseno do CLIP depois
        referencia: tuple[int | None, int, str] | None = None
        if imagem is not None and referencias:
            melhor_ref: tuple[int, int | None, str] = (0, None, "")
            for r in referencias:
                d = img_mod.distancia(imagem.phash, r.phash)
                if d <= LIMIAR_PHASH_IGUAL:
                    melhor_ref = max(melhor_ref, (100, r.id, f"phash d={d}"))
                    continue
                if embedding is not None and r.embedding is not None:
                    cos = clip_mod.similaridade(embedding, r.embedding)
                    val = int(round(max(0.0, min(1.0, (cos - COSSENO_ZERO) / (COSSENO_CEM - COSSENO_ZERO))) * 100))
                    melhor_ref = max(melhor_ref, (val, r.id, f"clip cos={cos:.3f}"))
            referencia = (melhor_ref[1], melhor_ref[0], melhor_ref[2])

        comp = Componentes(
            lexico=av.score,
            visual=int(round(visual["cartaz"] * 100)) if visual else None,
            referencia=referencia[1] if referencia else None,
            monitor=100 if termos_monitor else 0,
            distribuicao=bool(qr or convites),
        )
        score, decomposicao = combinar(comp, pesos_de(prefs))
        sev = severidade(score, av.nao_pacifico, av.score, prefs.convocacoesLimiarAlerta, prefs.convocacoesLimiarCritico)
        caps = {"ocr": res_ocr is not None, "clip": visual is not None, "ocr_modelo": res_ocr.modelo if res_ocr else None}
        return Analise(
            imagem=imagem,
            ocr=res_ocr,
            qr=qr,
            convites=convites,
            lexico=av,
            visual=visual,
            embedding=embedding,
            referencia=referencia,
            termos_monitor=termos_monitor,
            componentes=comp,
            score=score,
            decomposicao=decomposicao,
            severidade=sev,
            ms=int((time.monotonic() - t0) * 1000),
            capacidades=caps,
        )


_analisador: Analisador | None = None


def get_analisador() -> Analisador:
    global _analisador
    if _analisador is None:
        _analisador = Analisador()
    return _analisador


def set_analisador(a: Analisador | None) -> None:
    global _analisador
    _analisador = a


def compilar_monitores(monitores: list) -> list[MonitorCompilado]:
    """Compila monitores ativos (tipo query/hashtag) para uso dentro da thread de análise."""
    out: list[MonitorCompilado] = []
    for m in monitores:
        if not getattr(m, "ativo", True) or m.id is None:
            continue
        mt = radar.compilar(m.query, getattr(m, "radar_modo", "termos"))
        if mt.tem_termos:
            out.append(MonitorCompilado(id=m.id, nome=m.nome, matcher=mt))
    return out
