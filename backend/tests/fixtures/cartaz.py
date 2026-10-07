"""Cartaz sintético (Pillow) para testes: fundo vermelho/preto, texto grande e QR opcional."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LINHAS_PADRAO = (
    ("GRITO DOS EXCLUÍDOS", 56, (200, 30, 30)),
    ("REVOLTA", 170, (200, 30, 30)),
    ("NAS RUAS", 150, (200, 30, 30)),
    ("DIA 11 DE OUTUBRO EM", 48, (230, 230, 230)),
    ("BELO HORIZONTE, MINAS GERAIS", 48, (230, 230, 230)),
    ("ATO NÃO PACÍFICO", 96, (200, 30, 30)),
)
_FONTES = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")


def _fonte(tamanho: int):  # noqa: ANN202
    for f in _FONTES:
        if Path(f).exists():
            return ImageFont.truetype(f, tamanho)
    return ImageFont.load_default(size=tamanho)


def fabricar_cartaz(linhas=LINHAS_PADRAO, tamanho=(1080, 1350), qr: str | None = None, formato: str = "PNG") -> bytes:  # noqa: ANN001
    w, h = tamanho
    img = Image.new("RGB", (w, h), (170, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([60, 60, w - 60, h - 60], fill=(10, 10, 10))
    y = 120
    for txt, sz, cor in linhas:
        f = _fonte(sz)
        bb = d.textbbox((0, 0), txt, font=f)
        d.text(((w - (bb[2] - bb[0])) // 2, y), txt, font=f, fill=cor)
        y += bb[3] - bb[1] + 40
    if qr:
        from app.services.convocacoes.imagem import gerar_qr

        q = gerar_qr(qr, lado=260)
        img.paste(q, (w - 60 - 260 - 20, h - 60 - 260 - 20))
    buf = io.BytesIO()
    img.save(buf, formato)
    return buf.getvalue()


def imagem_neutra(tamanho=(640, 480)) -> bytes:  # noqa: ANN001
    img = Image.new("RGB", tamanho, (30, 120, 200))
    d = ImageDraw.Draw(img)
    d.ellipse([100, 100, 500, 400], fill=(240, 200, 40))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()
