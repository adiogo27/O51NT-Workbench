"""Scraper ÉTICO para páginas públicas (trends24 via httpx; OneMillionTweetMap via Playwright).

Busca em buscadores NÃO passa por aqui: é feita pela instância local do SearXNG
(`services/searxng_client.py`), porque DuckDuckGo/Bing proíbem crawling no robots.txt.

Regras (documento de premissas, seção 5):
- apenas dados públicos, sem login, sem burlar paywall/captcha;
- robots.txt sempre respeitado (urllib.robotparser);
- 1 requisição / 3 s por domínio, fila global (asyncio.Queue), concorrência 2;
- User-Agent identificável;
- 403/429 → domínio em backoff persistente com TTL exponencial (1h → 6h → 24h);
- todo resultado carrega URL de origem + timestamp + SHA-256.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from typing import Protocol
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.config import get_settings

logger = logging.getLogger("o51nt.scraper")

BACKOFF_TTLS: tuple[timedelta, ...] = (timedelta(hours=1), timedelta(hours=6), timedelta(hours=24))


@dataclass(slots=True)
class ResultadoScrape:
    url: str
    status: int
    html: str = ""
    sha256: str = ""
    coletado_em: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    erro: str | None = None
    via: str = ""

    @property
    def ok(self) -> bool:
        return self.erro is None and 200 <= self.status < 300


@dataclass(slots=True)
class ResultadoBytes:
    """Resultado binário (imagens, fotos de grupo). Mesmas garantias de ResultadoScrape: URL, horário, SHA-256."""

    url: str
    status: int
    conteudo: bytes = b""
    mime: str = ""
    sha256: str = ""
    coletado_em: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    erro: str | None = None
    via: str = ""

    @property
    def ok(self) -> bool:
        return self.erro is None and 200 <= self.status < 300 and bool(self.conteudo)


class Fetcher(Protocol):
    nome: str

    async def get(self, url: str, timeout: float) -> tuple[int, str]: ...

    async def close(self) -> None: ...

    # opcional (detectado por hasattr): download binário em streaming com limite de bytes
    # async def get_bytes(self, url: str, timeout: float, limite: int) -> tuple[int, bytes, str]: ...


class HttpxFetcher:
    """Fetcher leve (sem JS) — usado para robots.txt e páginas HTML estáticas."""

    nome = "httpx"

    def __init__(self, user_agent: str) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept-Language": "pt-BR,pt;q=0.9"},
            follow_redirects=True,
        )

    async def get(self, url: str, timeout: float) -> tuple[int, str]:
        r = await self._client.get(url, timeout=timeout)
        return r.status_code, r.text

    async def get_bytes(self, url: str, timeout: float, limite: int) -> tuple[int, bytes, str]:
        """Streaming com limite: aborta assim que exceder `limite` (ValueError)."""
        async with self._client.stream("GET", url, timeout=timeout) as r:
            mime = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
            tam = int(r.headers.get("content-length") or 0)
            if tam > limite:
                raise ValueError(f"conteúdo excede o limite de {limite // (1024 * 1024)} MB")
            partes: list[bytes] = []
            total = 0
            async for bloco in r.aiter_bytes():
                total += len(bloco)
                if total > limite:
                    raise ValueError(f"conteúdo excede o limite de {limite // (1024 * 1024)} MB")
                partes.append(bloco)
            return r.status_code, b"".join(partes), mime

    async def close(self) -> None:
        await self._client.aclose()


def detectar_chromium() -> str | None:
    """Executável do Chromium do sistema (fallback quando `playwright install` não foi rodado)."""
    if env := os.environ.get("O51NT_CHROMIUM"):
        return env
    for nome in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        if caminho := shutil.which(nome):
            return caminho
    return None


class PlaywrightFetcher:
    """Chromium headless via Playwright, para páginas que exigem JavaScript (OneMillionTweetMap)."""

    nome = "playwright"

    def __init__(self, user_agent: str) -> None:
        self._ua = user_agent
        self._pw = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> None:
        async with self._lock:
            if self._browser is not None:
                return
            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
            try:
                self._browser = await self._pw.chromium.launch(headless=True)
            except Exception:  # navegador do Playwright não instalado → usa o do sistema
                exe = detectar_chromium()
                if exe is None:
                    raise
                self._browser = await self._pw.chromium.launch(headless=True, executable_path=exe)

    async def get(self, url: str, timeout: float) -> tuple[int, str]:
        await self._ensure()
        assert self._browser is not None
        ctx = await self._browser.new_context(user_agent=self._ua, java_script_enabled=True)
        try:
            page = await ctx.new_page()
            resp = await page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
            status = resp.status if resp else 0
            return status, await page.content()
        finally:
            await ctx.close()

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()
        self._browser = self._pw = None


# ------------------------------------------------------------------ backoff
class BackoffStore(Protocol):
    def bloqueado_ate(self, dominio: str) -> datetime | None: ...

    def registrar(self, dominio: str, status: int) -> datetime: ...

    def limpar(self, dominio: str) -> None: ...

    def listar(self) -> dict[str, dict]: ...


def _ttl(nivel: int) -> timedelta:
    return BACKOFF_TTLS[min(nivel, len(BACKOFF_TTLS)) - 1]


class MemoryBackoffStore:
    """Usado nos testes unitários do scraper."""

    def __init__(self) -> None:
        self._d: dict[str, tuple[datetime, int, int]] = {}

    def bloqueado_ate(self, dominio: str) -> datetime | None:
        item = self._d.get(dominio)
        return item[0] if item and item[0] > datetime.now(UTC) else None

    def registrar(self, dominio: str, status: int) -> datetime:
        nivel = self._d[dominio][1] + 1 if dominio in self._d else 1
        ate = datetime.now(UTC) + _ttl(nivel)
        self._d[dominio] = (ate, nivel, status)
        return ate

    def limpar(self, dominio: str) -> None:
        self._d.pop(dominio, None)

    def listar(self) -> dict[str, dict]:
        return {d: {"retry_after": a.isoformat(), "nivel": n, "status": s} for d, (a, n, s) in self._d.items()}


class SqliteBackoffStore:
    """Persistente na tabela `domain_backoff` (sobrevive a reinícios)."""

    @staticmethod
    def _aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

    def bloqueado_ate(self, dominio: str) -> datetime | None:
        from sqlmodel import Session

        from app.db import get_engine
        from app.models.backoff import DomainBackoff

        with Session(get_engine()) as s:
            row = s.get(DomainBackoff, dominio)
            if row is None:
                return None
            ate = self._aware(row.retry_after)
            return ate if ate > datetime.now(UTC) else None

    def registrar(self, dominio: str, status: int) -> datetime:
        from sqlmodel import Session

        from app.db import get_engine
        from app.models._base import agora
        from app.models.backoff import DomainBackoff

        with Session(get_engine()) as s:
            row = s.get(DomainBackoff, dominio)
            nivel = (row.nivel + 1) if row else 1
            ate = datetime.now(UTC) + _ttl(nivel)
            if row is None:
                row = DomainBackoff(domain=dominio, retry_after=ate, nivel=nivel, ultimo_status=status)
            else:
                row.retry_after, row.nivel, row.ultimo_status, row.atualizado_em = ate, nivel, status, agora()
            s.add(row)
            s.commit()
            return ate

    def limpar(self, dominio: str) -> None:
        from sqlmodel import Session

        from app.db import get_engine
        from app.models.backoff import DomainBackoff

        with Session(get_engine()) as s:
            row = s.get(DomainBackoff, dominio)
            if row is not None:
                s.delete(row)
                s.commit()

    def listar(self) -> dict[str, dict]:
        from sqlmodel import Session, select

        from app.db import get_engine
        from app.models.backoff import DomainBackoff

        with Session(get_engine()) as s:
            return {
                r.domain: {"retry_after": self._aware(r.retry_after).isoformat(), "nivel": r.nivel, "status": r.ultimo_status}
                for r in s.exec(select(DomainBackoff)).all()
            }


# ------------------------------------------------------------------ robots / rate-limit
class RobotsCache:
    def __init__(self, fetcher: Fetcher, user_agent: str, ttl: float = 3600.0) -> None:
        self._fetcher = fetcher
        self._ua = user_agent
        self._ttl = ttl
        self._cache: dict[str, tuple[float, RobotFileParser | None]] = {}

    async def permitido(self, url: str) -> bool:
        partes = urlsplit(url)
        base = f"{partes.scheme}://{partes.netloc}"
        agora = time.monotonic()
        item = self._cache.get(base)
        if item is None or agora - item[0] > self._ttl:
            parser: RobotFileParser | None = RobotFileParser()
            try:
                status, texto = await self._fetcher.get(base + "/robots.txt", 10.0)
            except Exception:
                status, texto = 0, ""
            if 200 <= status < 300:
                assert parser is not None
                parser.parse(texto.splitlines())
            elif 400 <= status < 500 and status not in (401, 403, 429):
                parser = None  # sem robots.txt → tudo permitido (RFC 9309)
            else:
                parser = RobotFileParser()
                parser.disallow_all = True  # erro de rede/5xx → conservador
            item = (agora, parser)
            self._cache[base] = item
        parser = item[1]
        return True if parser is None else parser.can_fetch(self._ua, url)


class RateLimiter:
    """Garante intervalo mínimo entre requisições ao mesmo domínio."""

    def __init__(self, intervalo: float) -> None:
        self._intervalo = intervalo
        self._ultimo: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def aguardar(self, dominio: str) -> None:
        lock = self._locks.setdefault(dominio, asyncio.Lock())
        async with lock:
            espera = self._ultimo.get(dominio, -1e9) + self._intervalo - time.monotonic()
            if espera > 0:
                await asyncio.sleep(espera)
            self._ultimo[dominio] = time.monotonic()


@dataclass(slots=True)
class _Job:
    url: str
    usar_js: bool
    futuro: asyncio.Future
    respeitar_robots: bool = True
    binario: bool = False
    limite_bytes: int = 0


class EthicalScraper:
    """Fila global com N workers; cada job passa por backoff → robots → rate-limit → fetch → hash."""

    def __init__(
        self,
        user_agent: str | None = None,
        intervalo: float | None = None,
        concorrencia: int | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        fetcher_estatico: Fetcher | None = None,
        fetcher_js: Fetcher | None = None,
        backoff: BackoffStore | None = None,
    ) -> None:
        s = get_settings()
        self.user_agent = user_agent or s.user_agent
        self.timeout = timeout if timeout is not None else s.scraper_timeout_seconds
        self.retries = retries if retries is not None else s.scraper_retries
        self.concorrencia = concorrencia or s.scraper_concurrency
        self._estatico: Fetcher = fetcher_estatico or HttpxFetcher(self.user_agent)
        self._js: Fetcher = fetcher_js or PlaywrightFetcher(self.user_agent)
        self.robots = RobotsCache(self._estatico, self.user_agent)
        self.rate = RateLimiter(intervalo if intervalo is not None else s.rate_limit_seconds)
        self.backoff: BackoffStore = backoff or SqliteBackoffStore()
        self._fila: asyncio.Queue[_Job] | None = None
        self._workers: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        if self._workers:
            return
        self._fila = asyncio.Queue()
        self._workers = [asyncio.create_task(self._worker()) for _ in range(self.concorrencia)]

    async def stop(self) -> None:
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        await self._estatico.close()
        await self._js.close()

    async def buscar(self, url: str, usar_js: bool = False, respeitar_robots: bool = True) -> ResultadoScrape:
        """`respeitar_robots=False` só para feeds pessoais assinados pelo analista (ex.: Google Alertas)."""
        await self.start()
        assert self._fila is not None
        futuro: asyncio.Future[ResultadoScrape] = asyncio.get_running_loop().create_future()
        await self._fila.put(_Job(url, usar_js, futuro, respeitar_robots))
        return await futuro

    async def buscar_bytes(self, url: str, respeitar_robots: bool = True, limite_bytes: int | None = None) -> ResultadoBytes:
        """Download binário (imagem/foto) pela mesma fila: backoff → robots → rate limit → fetch → sha256."""
        await self.start()
        assert self._fila is not None
        limite = limite_bytes or get_settings().max_download_mb * 1024 * 1024
        futuro: asyncio.Future[ResultadoBytes] = asyncio.get_running_loop().create_future()
        await self._fila.put(_Job(url, False, futuro, respeitar_robots, binario=True, limite_bytes=limite))
        return await futuro

    async def _worker(self) -> None:
        assert self._fila is not None
        while True:
            job = await self._fila.get()
            try:
                if job.binario:
                    res = await self._processar_bytes(job.url, job.respeitar_robots, job.limite_bytes)
                else:
                    res = await self._processar(job.url, job.usar_js, job.respeitar_robots)
            except Exception as exc:  # nunca derruba o worker
                if job.binario:
                    res = ResultadoBytes(url=job.url, status=0, erro=f"falha inesperada: {exc}")
                else:
                    res = ResultadoScrape(url=job.url, status=0, erro=f"falha inesperada: {exc}")
            if not job.futuro.done():
                job.futuro.set_result(res)
            self._fila.task_done()

    async def _processar(self, url: str, usar_js: bool, respeitar_robots: bool = True) -> ResultadoScrape:
        dominio = urlsplit(url).netloc.lower()
        if ate := self.backoff.bloqueado_ate(dominio):
            return self._log(ResultadoScrape(url=url, status=0, erro=f"domínio em backoff até {ate.isoformat()}"))
        if respeitar_robots and not await self.robots.permitido(url):
            return self._log(ResultadoScrape(url=url, status=0, erro="bloqueado por robots.txt"))
        fetcher = self._js if usar_js else self._estatico
        ultimo_erro = ""
        for tentativa in range(self.retries + 1):
            await self.rate.aguardar(dominio)
            try:
                status, html = await asyncio.wait_for(fetcher.get(url, self.timeout), self.timeout + 5)
            except Exception as exc:
                ultimo_erro = f"{type(exc).__name__}: {exc}"
                continue
            if status in (403, 429):
                ate = self.backoff.registrar(dominio, status)
                return self._log(
                    ResultadoScrape(url=url, status=status, erro=f"HTTP {status} — domínio em backoff até {ate.isoformat()}", via=fetcher.nome)
                )
            if status >= 500 and tentativa < self.retries:
                ultimo_erro = f"HTTP {status}"
                continue
            if 200 <= status < 300:
                self.backoff.limpar(dominio)  # sucesso zera a escada de TTL
            res = ResultadoScrape(
                url=url,
                status=status,
                html=html,
                sha256=hashlib.sha256(html.encode("utf-8", "replace")).hexdigest(),
                erro=None if 200 <= status < 300 else f"HTTP {status}",
                via=fetcher.nome,
            )
            return self._log(res)
        return self._log(ResultadoScrape(url=url, status=0, erro=ultimo_erro or "falha", via=fetcher.nome))

    async def _processar_bytes(self, url: str, respeitar_robots: bool, limite: int) -> ResultadoBytes:
        dominio = urlsplit(url).netloc.lower()
        if ate := self.backoff.bloqueado_ate(dominio):
            return self._log(ResultadoBytes(url=url, status=0, erro=f"domínio em backoff até {ate.isoformat()}"))
        if respeitar_robots and not await self.robots.permitido(url):
            return self._log(ResultadoBytes(url=url, status=0, erro="bloqueado por robots.txt"))
        fetcher = self._estatico
        ultimo_erro = ""
        for tentativa in range(self.retries + 1):
            await self.rate.aguardar(dominio)
            try:
                if hasattr(fetcher, "get_bytes"):
                    status, conteudo, mime = await asyncio.wait_for(fetcher.get_bytes(url, self.timeout, limite), self.timeout + 5)
                else:  # fetcher só de texto: usa o texto como bytes
                    status, texto = await asyncio.wait_for(fetcher.get(url, self.timeout), self.timeout + 5)
                    conteudo, mime = texto.encode("utf-8", "replace"), "text/html"
            except ValueError as exc:  # limite de tamanho: não adianta repetir
                return self._log(ResultadoBytes(url=url, status=0, erro=str(exc), via=fetcher.nome))
            except Exception as exc:
                ultimo_erro = f"{type(exc).__name__}: {exc}"
                continue
            if status in (403, 429):
                ate = self.backoff.registrar(dominio, status)
                return self._log(ResultadoBytes(url=url, status=status, erro=f"HTTP {status} — domínio em backoff até {ate.isoformat()}", via=fetcher.nome))
            if status >= 500 and tentativa < self.retries:
                ultimo_erro = f"HTTP {status}"
                continue
            if 200 <= status < 300:
                self.backoff.limpar(dominio)
            return self._log(
                ResultadoBytes(
                    url=url, status=status, conteudo=conteudo if 200 <= status < 300 else b"", mime=mime,
                    sha256=hashlib.sha256(conteudo).hexdigest(), erro=None if 200 <= status < 300 else f"HTTP {status}", via=fetcher.nome,
                )
            )
        return self._log(ResultadoBytes(url=url, status=0, erro=ultimo_erro or "falha", via=fetcher.nome))

    @staticmethod
    def _log(res):  # noqa: ANN001, ANN205
        dados: dict[str, object] = {"url": res.url, "status": res.status, "via": res.via}
        if isinstance(res, ResultadoBytes):
            dados["bytes"] = len(res.conteudo)
        if res.sha256:
            dados["sha256"] = res.sha256
        if res.erro:  # chave só existe quando há erro (mesma regra do searxng_client)
            dados["erro"] = res.erro
        logger.log(logging.WARNING if res.erro else logging.INFO, "scrape", extra={"dados": dados})
        return res


# ------------------------------------------------------------------ extratores

_HASHTAG_RE = re.compile(r"(?<![\w&/])#([\wÀ-ÿ]{2,100})")


def extrair_convites(html: str) -> list[tuple[str, str]]:
    """Retorna [(plataforma, url_canônica)] sem duplicatas, na ordem em que aparecem. (Delegado a services.convites — v2.)"""
    from app.services.convites import extrair_convites as _v2

    return _v2(html)


def extrair_hashtags(html: str) -> dict[str, int]:
    """Conta hashtags em HTML público (ex.: trends24.in). Remove tags/script antes."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for el in soup(["script", "style", "noscript"]):
        el.decompose()
    contagem: dict[str, int] = {}
    for m in _HASHTAG_RE.finditer(soup.get_text(" ")):
        tag = "#" + m.group(1)
        contagem[tag] = contagem.get(tag, 0) + 1
    return contagem


FONTES_HASHTAGS: dict[str, str] = {
    "trends24": "https://trends24.in/brazil/",
    "onemilliontweetmap": "https://onemilliontweetmap.com/",
}

# ----------------------------------------------------------- singleton do app

_scraper: EthicalScraper | None = None


def get_scraper() -> EthicalScraper:
    global _scraper
    if _scraper is None:
        _scraper = EthicalScraper()
    return _scraper


def set_scraper(s: EthicalScraper | None) -> None:
    global _scraper
    _scraper = s


async def shutdown_scraper() -> None:
    global _scraper
    if _scraper is not None:
        await _scraper.stop()
        _scraper = None
