from __future__ import annotations

import pytest

from app.services.convocacoes import imagem as im
from tests.fixtures.cartaz import fabricar_cartaz, imagem_neutra

pytestmark = pytest.mark.unit
WA = "https://chat.whatsapp.com/GM4b5kGzIFm36GoyM7AOlM"


def test_abrir_normaliza_e_hashes() -> None:
    dados = fabricar_cartaz()
    img = im.abrir(dados)
    assert max(img.largura, img.altura) <= im.LADO_MAX and img.mime == "image/png"
    assert len(img.phash) == 16 and len(img.sha256) == 64 and img.tamanho == len(dados)
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.open(io.BytesIO(dados)).convert("RGB").resize((540, 675)).save(buf, "JPEG", quality=70)
    menor = im.abrir(buf.getvalue())
    assert im.distancia(img.phash, menor.phash) <= 6  # mesma arte redimensionada/recomprimida
    assert im.distancia(img.phash, im.abrir(imagem_neutra()).phash) > 12


def test_abrir_rejeita_nao_imagem() -> None:
    with pytest.raises(ValueError):
        im.abrir(b"<html>nao sou imagem</html>")
    with pytest.raises(ValueError):
        im.abrir(b"")


def test_preprocessamento_gera_4_variantes_e_miniatura() -> None:
    img = im.abrir(fabricar_cartaz(tamanho=(540, 675)))
    vs = im.preprocessar_para_ocr(img)
    assert len(vs) == 4 and vs[1].shape[0] == img.altura * 2  # upscale 2x quando pequena
    th = im.miniatura_jpeg(img, 200)
    assert th[:2] == b"\xff\xd8" and len(th) < 60_000


def test_qr_code_e_lido() -> None:
    img = im.abrir(fabricar_cartaz(qr=WA))
    assert WA in im.ler_qr(img)
    assert im.ler_qr(im.abrir(imagem_neutra())) == []
