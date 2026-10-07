"""Abertura/normalização (Pillow), hashes perceptuais (imagehash) e pré-processamento + QR (OpenCV)."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

LADO_MAX = 1600
MAX_PIXELS = 25_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass(slots=True)
class ImagemNormalizada:
    pil: Image.Image  # RGB, lado maior ≤ LADO_MAX
    largura: int
    altura: int
    sha256: str  # dos bytes originais
    phash: str  # hex (imagehash.phash, 64 bits)
    dhash: str
    mime: str
    tamanho: int  # bytes originais

    @property
    def array_bgr(self) -> np.ndarray:
        return np.ascontiguousarray(np.asarray(self.pil)[:, :, ::-1])


_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif", "BMP": "image/bmp", "TIFF": "image/tiff"}


def abrir(dados: bytes) -> ImagemNormalizada:
    """Valida e normaliza. ValueError se não for imagem raster suportada ou exceder MAX_PIXELS."""
    import imagehash

    if not dados:
        raise ValueError("imagem vazia")
    try:
        im = Image.open(io.BytesIO(dados))
        im.load()
    except Image.DecompressionBombError as exc:
        raise ValueError("imagem grande demais") from exc
    except Exception as exc:  # PIL levanta UnidentifiedImageError / OSError
        raise ValueError(f"não é uma imagem suportada: {type(exc).__name__}") from exc
    formato = (im.format or "").upper()
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)  # GIF/WEBP animados: só o primeiro quadro
    im = ImageOps.exif_transpose(im) or im
    if im.width * im.height > MAX_PIXELS:
        raise ValueError("imagem excede 25 megapixels")
    rgb = im.convert("RGB")
    maior = max(rgb.width, rgb.height)
    if maior > LADO_MAX:
        esc = LADO_MAX / maior
        rgb = rgb.resize((max(1, round(rgb.width * esc)), max(1, round(rgb.height * esc))), Image.Resampling.LANCZOS)
    return ImagemNormalizada(
        pil=rgb,
        largura=rgb.width,
        altura=rgb.height,
        sha256=hashlib.sha256(dados).hexdigest(),
        phash=str(imagehash.phash(rgb)),
        dhash=str(imagehash.dhash(rgb)),
        mime=_MIME.get(formato, f"image/{formato.lower()}" if formato else "application/octet-stream"),
        tamanho=len(dados),
    )


def distancia(h1: str, h2: str) -> int:
    """Distância de Hamming entre dois hashes hex (phash/dhash). 0 = idênticos; ≤ 6 = mesma imagem (recorte/recompressão)."""
    import imagehash

    try:
        return int(imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2))
    except (ValueError, TypeError):
        return 64


def preprocessar_para_ocr(img: ImagemNormalizada) -> list[np.ndarray]:
    """Variantes BGR para o OCR: original, cinza ampliada (2x se pequena), Otsu e invertida (texto claro em fundo escuro/vermelho)."""
    import cv2

    cv2.setNumThreads(min(2, cv2.getNumThreads() or 2))
    base = img.array_bgr
    variantes = [base]
    cinza = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    if max(img.largura, img.altura) < 1200:
        cinza = cv2.resize(cinza, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    variantes.append(cv2.cvtColor(cinza, cv2.COLOR_GRAY2BGR))
    _, otsu = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variantes.append(cv2.cvtColor(otsu, cv2.COLOR_GRAY2BGR))
    variantes.append(cv2.cvtColor(255 - cinza, cv2.COLOR_GRAY2BGR))
    return variantes


def ler_qr(img: ImagemNormalizada) -> list[str]:
    """Decodifica QR codes (cv2.QRCodeDetector) na imagem e numa versão ampliada. Sem duplicatas."""
    import cv2

    det = cv2.QRCodeDetector()
    achados: list[str] = []
    base = img.array_bgr
    candidatos = [base]
    if max(img.largura, img.altura) < 1000:
        candidatos.append(cv2.resize(base, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC))
    for arr in candidatos:
        try:
            ok, textos, _pontos, _ret = det.detectAndDecodeMulti(arr)
        except cv2.error:
            ok, textos = False, []
        if ok:
            for t in textos:
                t = (t or "").strip()
                if t and t not in achados:
                    achados.append(t)
        if not achados:
            try:
                t, _p, _r = det.detectAndDecode(arr)
            except cv2.error:
                t = ""
            t = (t or "").strip()
            if t and t not in achados:
                achados.append(t)
    return achados


def miniatura_jpeg(img: ImagemNormalizada, lado: int = 320) -> bytes:
    th = img.pil.copy()
    th.thumbnail((lado, lado), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    th.save(buf, "JPEG", quality=82, optimize=True)
    return buf.getvalue()


def gerar_qr(texto: str, lado: int = 220) -> Image.Image:
    """QR code como imagem PIL (usado em testes e para pré-visualização). Requer cv2.QRCodeEncoder."""
    import cv2

    enc = cv2.QRCodeEncoder.create()
    arr = enc.encode(texto)
    im = Image.fromarray(arr).convert("RGB")
    return im.resize((lado, lado), Image.Resampling.NEAREST)
