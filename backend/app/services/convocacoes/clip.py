"""CLIP (open_clip + PyTorch CPU): zero-shot "cartaz × meme × foto × notícia" e embeddings para similaridade.

Perfil "completo" (opt-in: ./run.sh --ml). Prompts em português pré-embutidos uma vez (data/models/clip_prompts_<modelo>.npy)
e a torre de texto é descartada após isso para economizar ~250 MB de RAM. Nada aqui identifica pessoas.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger("o51nt.convocacoes.clip")

PROMPTS: dict[str, str] = {
    "cartaz": "um cartaz ou panfleto convocando para um protesto, manifestação ou ato político, com texto grande",
    "meme": "um meme de internet com texto engraçado",
    "foto": "uma fotografia de pessoas, de uma rua ou de um lugar",
    "noticia": "uma captura de tela de uma notícia de jornal ou de um site",
    "outro": "uma imagem qualquer",
}
MODELO_PADRAO = "ViT-B-32"
PRETRAINED_PADRAO = "laion2b_s34b_b79k"


def disponivel() -> bool:
    return importlib.util.find_spec("open_clip") is not None and importlib.util.find_spec("torch") is not None


class MotorCLIP:
    def __init__(self, dir_modelos: Path, modelo: str = MODELO_PADRAO, pretrained: str = PRETRAINED_PADRAO, threads: int = 4) -> None:
        import open_clip
        import torch

        torch.set_num_threads(threads)
        dir_modelos.mkdir(parents=True, exist_ok=True)
        self.nome = f"{modelo}/{pretrained}"
        self._torch = torch
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(modelo, pretrained=pretrained, cache_dir=str(dir_modelos / "open_clip"))
        self._model.eval()
        cache = dir_modelos / f"clip_prompts_{modelo}_{pretrained}.npy"
        if cache.exists():
            self._prompts = np.load(cache)
        else:
            tok = open_clip.get_tokenizer(modelo)
            with torch.no_grad():
                emb = self._model.encode_text(tok(list(PROMPTS.values())))
                emb = emb / emb.norm(dim=-1, keepdim=True)
            self._prompts = emb.cpu().numpy().astype(np.float32)
            np.save(cache, self._prompts)
        # libera a torre de texto (só precisamos da visual daqui em diante)
        for attr in ("transformer", "token_embedding", "positional_embedding", "ln_final", "text_projection"):
            if hasattr(self._model, attr):
                try:
                    setattr(self._model, attr, None)
                except Exception:
                    pass

    def embutir(self, pil: Image.Image) -> np.ndarray:
        with self._torch.no_grad():
            x = self._preprocess(pil.convert("RGB")).unsqueeze(0)
            e = self._model.encode_image(x)
            e = e / e.norm(dim=-1, keepdim=True)
        return e[0].cpu().numpy().astype(np.float32)

    def classificar(self, emb: np.ndarray) -> dict[str, float]:
        logits = 100.0 * (self._prompts @ emb)
        p = np.exp(logits - logits.max())
        p /= p.sum()
        return {k: round(float(v), 4) for k, v in zip(PROMPTS.keys(), p, strict=True)}


def similaridade(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
