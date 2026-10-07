"""OCR em CPU via rapidocr (ONNX Runtime). Opcional: `disponivel()` indica se o pacote está instalado.

Modelo de reconhecimento `latin` (PP-OCRv5) cobre português com acentos; baixado uma vez para data/models/rapidocr.
Sem rede na primeira carga, cai para o modelo ch/en (letras latinas OK, acentos perdidos — irrelevante para o léxico,
que compara sem acentos).
"""

from __future__ import annotations

import importlib.util
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger("o51nt.convocacoes.ocr")


def disponivel() -> bool:
    return importlib.util.find_spec("rapidocr") is not None and importlib.util.find_spec("onnxruntime") is not None


@dataclass(slots=True)
class ResultadoOCR:
    texto: str = ""
    linhas: list[str] = field(default_factory=list)
    confianca: float = 0.0
    variante: int = 0
    ms: int = 0
    modelo: str = ""


class MotorOCR:
    def __init__(self, dir_modelos: Path, threads: int = 4) -> None:
        from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

        dir_modelos.mkdir(parents=True, exist_ok=True)
        base = {
            "Global.log_level": "warning",
            "Global.model_root_dir": str(dir_modelos),
            "EngineConfig.onnxruntime.intra_op_num_threads": threads,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        }
        try:
            self._engine = RapidOCR(params={**base, "Rec.lang_type": LangRec.LATIN, "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.model_type": ModelType.MOBILE})
            self.modelo = "latin"
        except Exception as exc:  # download do modelo latin falhou (offline) → modelo padrão já embutido
            logger.warning("OCR latin indisponível, usando ch/en", extra={"dados": {"erro": str(exc)}})
            self._engine = RapidOCR(params=base)
            self.modelo = "ch_en"

    def _ler_uma(self, arr: np.ndarray) -> tuple[list[str], float]:
        res = self._engine(arr)
        txts = list(res.txts or ())
        scores = list(res.scores or ())
        conf = float(sum(scores) / len(scores)) if scores else 0.0
        return txts, conf

    def ler(self, variantes: list[np.ndarray], minimo_linhas: int = 1) -> ResultadoOCR:
        """Lê cada variante e fica com a de melhor (nº de linhas, confiança média). Para cedo se a 1ª já for boa."""
        t0 = time.monotonic()
        melhor = ResultadoOCR(modelo=self.modelo)
        for i, arr in enumerate(variantes):
            try:
                linhas, conf = self._ler_uma(arr)
            except Exception as exc:
                logger.warning("falha no OCR", extra={"dados": {"variante": i, "erro": str(exc)}})
                continue
            cand = ResultadoOCR(texto="\n".join(linhas), linhas=linhas, confianca=round(conf, 4), variante=i, modelo=self.modelo)
            if (len(cand.linhas), cand.confianca) > (len(melhor.linhas), melhor.confianca):
                melhor = cand
            if i == 0 and len(cand.linhas) >= 3 and cand.confianca >= 0.9:
                break  # original já legível; evita 3 passagens extras
        melhor.ms = int((time.monotonic() - t0) * 1000)
        return melhor
