from __future__ import annotations

import pytest

from app.services import scraper as mod
from app.services.scraper import MemoryBackoffStore
from tests.conftest import FakeFetcher

pytestmark = pytest.mark.unit


async def test_buscar_bytes_ok_limite_e_robots(data_dir) -> None:  # noqa: ANN001
    f = FakeFetcher()
    f.binarios["https://cdn.test/a.jpg"] = (200, b"\xff\xd8" + b"x" * 100, "image/jpeg")
    f.binarios["https://cdn.test/grande.jpg"] = (200, b"x" * 5000, "image/jpeg")
    f.paginas["https://bloq.test/robots.txt"] = (200, "User-agent: *\nDisallow: /\n")
    f.binarios["https://bloq.test/x.jpg"] = (200, b"img", "image/jpeg")
    s = mod.EthicalScraper(intervalo=0, fetcher_estatico=f, fetcher_js=f, retries=0, backoff=MemoryBackoffStore())
    try:
        r = await s.buscar_bytes("https://cdn.test/a.jpg")
        assert r.ok and r.mime == "image/jpeg" and len(r.conteudo) == 102 and len(r.sha256) == 64
        g = await s.buscar_bytes("https://cdn.test/grande.jpg", limite_bytes=1000)
        assert not g.ok and "excede" in (g.erro or "")
        b = await s.buscar_bytes("https://bloq.test/x.jpg")
        assert not b.ok and "robots" in (b.erro or "")
        b2 = await s.buscar_bytes("https://bloq.test/x.jpg", respeitar_robots=False)
        assert b2.ok and b2.conteudo == b"img"
        nf = await s.buscar_bytes("https://cdn.test/nada.jpg")
        assert not nf.ok and nf.status == 404 and nf.conteudo == b""
    finally:
        await s.stop()


async def test_buscar_bytes_fallback_fetcher_so_texto(data_dir) -> None:  # noqa: ANN001
    class SoTexto:
        nome = "txt"

        async def get(self, url: str, timeout: float) -> tuple[int, str]:
            return (404, "") if url.endswith("robots.txt") else (200, "<html>oi</html>")

        async def close(self) -> None:
            return None

    s = mod.EthicalScraper(intervalo=0, fetcher_estatico=SoTexto(), fetcher_js=SoTexto(), retries=0, backoff=MemoryBackoffStore())
    try:
        r = await s.buscar_bytes("https://t.test/p")
        assert r.ok and r.conteudo == b"<html>oi</html>" and r.mime == "text/html"
    finally:
        await s.stop()
