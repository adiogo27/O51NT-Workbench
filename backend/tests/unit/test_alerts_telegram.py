from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from httpx import Response

from app import config
from app.services import alerts

pytestmark = pytest.mark.unit

API = "https://api.telegram.org"


@pytest.fixture
def telegram_env(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "371824016")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_sem_token_nao_esta_configurado(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    config.get_settings.cache_clear()
    assert alerts.telegram_configurado() is False


def test_prefixo_o51nt_tambem_vale(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("O51NT_TELEGRAM_BOT_TOKEN", "1:x")
    monkeypatch.setenv("O51NT_TELEGRAM_CHAT_ID", "9")
    config.get_settings.cache_clear()
    assert alerts.telegram_configurado() is True


def test_formatar_radar_escapa_html_e_lista_hits() -> None:
    ev = {
        "tipo": "radar",
        "nome": "PRF <blitz> & rodovias",
        "query": 'PRF "blitz"',
        "novos_hits": 7,
        "hits": [{"titulo": f"Notícia {i} <b>", "url": f"https://ex.org/n{i}?a=1&b=2", "fonte": "g1"} for i in range(7)],
        "executado_em": "2026-10-09T12:00:00+00:00",
    }
    txt = alerts.formatar_telegram(ev)
    assert txt.startswith("📡 <b>O51NT</b> · radar")
    assert "PRF &lt;blitz&gt; &amp; rodovias" in txt and "<blitz>" not in txt
    assert txt.count("• ") == 5 and "… e mais 2" in txt
    assert '<a href="https://ex.org/n0?a=1&amp;b=2">Notícia 0 &lt;b&gt;</a> — g1' in txt
    assert "<i>2026-10-09 12:00:00</i>" in txt


def test_formatar_convocacao_e_monitor_simples() -> None:
    conv = alerts.formatar_telegram({"tipo": "convocacao", "severidade": "critica", "titulo": "Cartaz de ato", "resumo": "x" * 500, "url": "https://ex.org/p"})
    assert conv.startswith("🚨 <b>O51NT</b> · convocacao · critica") and len(conv) < 700
    mon = alerts.formatar_telegram({"nome": "Redes", "query": "PRF", "deeplinks": {"google": "https://g/?q=PRF", "x": "https://x.com/search?q=PRF"}})
    assert "abrir no Google" in mon and 'href="https://x.com/search?q=PRF"' in mon


def test_formatar_trunca_em_4000() -> None:
    txt = alerts.formatar_telegram({"titulo": "t", "resumo": "y" * 10, "hits": [{"titulo": "z" * 100, "url": "https://e/" + "u" * 100} for _ in range(5)], "query": "q" * 300, "url": "https://" + "w" * 3900})
    assert len(txt) <= alerts.TELEGRAM_MAX


async def test_enviar_telegram_sucesso_e_erro(telegram_env: None) -> None:
    with respx.mock(base_url=API) as mock:
        rota = mock.post("/bot123:ABC/sendMessage").mock(return_value=Response(200, json={"ok": True, "result": {"message_id": 42}}))
        r = await alerts.enviar_telegram("<b>oi</b>")
        assert r == {"ok": True, "status": 200, "message_id": 42}
        corpo = json.loads(rota.calls.last.request.content)
        assert corpo["chat_id"] == "371824016" and corpo["parse_mode"] == "HTML" and corpo["disable_web_page_preview"] is True
        mock.post("/bot123:ABC/sendMessage").mock(return_value=Response(401, json={"ok": False, "description": "Unauthorized"}))
        r = await alerts.enviar_telegram("x")
        assert r["ok"] is False and r["erro"] == "Unauthorized" and r["status"] == 401


async def test_disparar_telegram_grava_jsonl_e_envia(telegram_env: None, data_dir: Path) -> None:
    with respx.mock(base_url=API) as mock:
        mock.post("/bot123:ABC/sendMessage").mock(return_value=Response(200, json={"ok": True, "result": {"message_id": 7}}))
        log = await alerts.disparar("telegram", {"tipo": "radar", "nome": "m", "novos_hits": 1, "hits": []})
    assert log == "telegram: enviado (msg 7)"
    assert list((data_dir / "alerts").glob("*.jsonl"))  # registro local preservado


async def test_disparar_telegram_nao_configurado_nao_levanta(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    config.get_settings.cache_clear()
    log = await alerts.disparar("telegram", {"titulo": "x"})
    assert log.startswith("telegram: falha (Telegram não configurado")


async def test_disparar_telegram_rede_fora_nao_levanta(telegram_env: None) -> None:
    import httpx

    with respx.mock(base_url=API) as mock:
        mock.post("/bot123:ABC/sendMessage").mock(side_effect=httpx.ConnectError("sem rede"))
        log = await alerts.disparar("telegram", {"titulo": "x"})
    assert log.startswith("telegram: falha (")
