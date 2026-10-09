from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.services import auth as auth_svc
from app.services import scheduler, scraper, searxng_client
from app.services.ia import cliente_openclaw


class FakeFetcher:
    """Fetcher em memória: {url: (status, html)}. robots.txt ausente → 404 (tudo permitido)."""

    nome = "fake"

    def __init__(self, paginas: dict[str, tuple[int, str]] | None = None) -> None:
        self.paginas = paginas or {}
        self.binarios: dict[str, tuple[int, bytes, str]] = {}  # {url: (status, bytes, mime)} para buscar_bytes
        self.chamadas: list[str] = []

    async def get(self, url: str, timeout: float) -> tuple[int, str]:
        self.chamadas.append(url)
        if url in self.paginas:
            return self.paginas[url]
        if url.endswith("/robots.txt"):
            return 404, ""
        return 404, "not found"

    async def get_bytes(self, url: str, timeout: float, limite: int) -> tuple[int, bytes, str]:
        self.chamadas.append(url)
        if url in self.binarios:
            status, dados, mime = self.binarios[url]
            if len(dados) > limite:
                raise ValueError(f"conteúdo excede o limite de {limite // (1024 * 1024)} MB")
            return status, dados, mime
        if url in self.paginas:
            status, html = self.paginas[url]
            return status, html.encode(), "text/html"
        return 404, b"", "text/plain"

    async def close(self) -> None:
        return None


class FakeSearxng:
    """Simula a API JSON do SearXNG: {query: [ {url,title,content}, ... ]}."""

    def __init__(self) -> None:
        self.respostas: dict[str, list[dict]] = {}
        self.status = 200
        self.consultas: list[dict[str, str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(200, text="OK")
        params = dict(request.url.params)
        self.consultas.append(params)
        if self.status != 200:
            return httpx.Response(self.status)
        return httpx.Response(200, json={"query": params.get("q"), "results": self.respostas.get(params.get("q", ""), []), "unresponsive_engines": []})


class FakeOpenClaw:
    """Simula o endpoint /v1/chat/completions do gateway OpenClaw: respostas por agent (FIFO; a última repete)."""

    def __init__(self) -> None:
        self.respostas: dict[str, list[Any]] = {}
        self.chamadas: list[dict[str, Any]] = []
        self.status = 200
        self.alcancavel = True

    def responder(self, agent: str, *respostas: Any) -> None:
        self.respostas.setdefault(agent, []).extend(respostas)

    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.alcancavel:
            raise httpx.ConnectError("gateway fora do ar", request=request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"ok": True, "status": "live"})
        if request.url.path != "/v1/chat/completions":
            return httpx.Response(404)
        if self.status != 200:
            return httpx.Response(self.status, text="erro simulado")
        corpo = json.loads(request.content)
        agent = str(corpo.get("model", "")).split("/", 1)[-1]
        self.chamadas.append({"agent": agent, "modelo": request.headers.get("x-openclaw-model"), "auth": request.headers.get("authorization"), "max_tokens": corpo.get("max_completion_tokens"), "mensagem": corpo["messages"][0]["content"]})
        fila = self.respostas.get(agent) or []
        if not fila:
            r: Any = {"veredito": "DESCARTAR", "severidade": "baixa", "justificativa": "sem resposta configurada"}
        elif len(fila) > 1:
            r = fila.pop(0)
        else:
            r = fila[0]
        texto = r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
        modelo = request.headers.get("x-openclaw-model") or "anthropic/claude-sonnet-5-5"
        return httpx.Response(200, json={"id": "chatcmpl-x", "model": modelo.split("/")[-1], "choices": [{"index": 0, "message": {"role": "assistant", "content": texto}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100}})


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Diretório de dados isolado por teste (permite rodar em paralelo com xdist)."""
    monkeypatch.setenv("O51NT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("O51NT_STATIC_DIR", str(tmp_path / "static"))
    monkeypatch.setenv("O51NT_SCHEDULER_ENABLED", "false")
    monkeypatch.delenv("O51NT_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    config.get_settings.cache_clear()
    db.set_engine(None)
    auth_svc.reset_cache()
    yield tmp_path / "data"
    eng = db._engine
    if eng is not None:
        eng.dispose()
    db.set_engine(None)
    scraper.set_scraper(None)
    searxng_client.set_searxng(None)
    scheduler.parar()
    cliente_openclaw.set_cliente(None)
    auth_svc.reset_cache()
    config.get_settings.cache_clear()


@pytest.fixture
def fake_fetcher() -> FakeFetcher:
    return FakeFetcher()


@pytest.fixture
def fake_scraper(data_dir: Path, fake_fetcher: FakeFetcher) -> scraper.EthicalScraper:
    s = scraper.EthicalScraper(intervalo=0, fetcher_estatico=fake_fetcher, fetcher_js=fake_fetcher, retries=1)
    scraper.set_scraper(s)
    return s


@pytest.fixture
def fake_searxng(data_dir: Path) -> FakeSearxng:
    fake = FakeSearxng()
    searxng_client.set_searxng(
        searxng_client.SearxngClient(base_url="http://searxng.test", transport=httpx.MockTransport(fake.handler))
    )
    return fake


@pytest.fixture
def fake_openclaw(data_dir: Path) -> FakeOpenClaw:
    fake = FakeOpenClaw()
    cliente_openclaw.set_cliente(cliente_openclaw.ClienteOpenClaw(base_url="http://openclaw.test", token="token-teste", transport=httpx.MockTransport(fake.handler)))
    return fake


@pytest.fixture
def client(data_dir: Path, fake_scraper: scraper.EthicalScraper, fake_searxng: FakeSearxng, fake_openclaw: FakeOpenClaw) -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
