"""Canal Telegram: status/teste em /api/settings/telegram e uso nos monitores (API externa simulada com respx)."""

from __future__ import annotations

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from app import config

pytestmark = pytest.mark.integration


def test_telegram_sem_configuracao(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    config.get_settings.cache_clear()
    st = client.get("/api/settings/telegram").json()
    assert st["configurado"] is False and "não configurado" in st["erro"] and st["bot"] is None
    assert client.post("/api/settings/telegram/teste").json()["ok"] is False
    r = client.post("/api/monitors", json={"nome": "t", "query": "PRF", "canal_alerta": "telegram"})
    assert r.status_code == 422 and "TELEGRAM_BOT_TOKEN" in r.json()["detail"]
    assert client.post("/api/hashtags/track", json={"tag": "#x", "canal_alerta": "telegram"}).status_code == 422
    # canal inválido continua recusado (contrato)
    assert client.post("/api/monitors", json={"nome": "t", "query": "PRF", "canal_alerta": "sms"}).status_code == 422


def test_telegram_configurado_status_teste_monitor_e_settings(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "371824016")
    config.get_settings.cache_clear()
    try:
        with respx.mock(base_url="https://api.telegram.org") as mock:
            mock.get("/bot123:ABC/getMe").mock(return_value=Response(200, json={"ok": True, "result": {"username": "alertao51ntbot", "first_name": "O51NT"}}))
            envio = mock.post("/bot123:ABC/sendMessage").mock(return_value=Response(200, json={"ok": True, "result": {"message_id": 5}}))
            st = client.get("/api/settings/telegram").json()
            assert st == {"configurado": True, "chat_id": "******016", "bot": "alertao51ntbot", "erro": None}
            assert client.post("/api/settings/telegram/teste").json() == {"ok": True, "status": 200, "message_id": 5}
            r = client.post("/api/monitors", json={"nome": "tg", "query": "PRF", "canal_alerta": "telegram"})
            assert r.status_code == 201 and r.json()["canal_alerta"] == "telegram"
            run = client.post(f"/api/monitors/{r.json()['id']}/run-now").json()
            assert "telegram: enviado (msg 5)" in run["log"]
            assert envio.call_count == 2
            # agenda e perfis também aceitam o canal
            eid = client.post("/api/agenda", json={"candidato": "C", "titulo": "Ato", "tipo": "ato", "data": "2026-10-10"}).json()["id"]
            assert client.post(f"/api/agenda/{eid}/monitor", json={"canal_alerta": "telegram"}).status_code == 201
            pid = client.post("/api/perfis", json={"rede": "x", "handle": "PRFBrasil"}).json()["id"]
            assert client.post(f"/api/perfis/{pid}/monitor", json={"canal_alerta": "telegram"}).status_code == 201
            cfg = client.get("/api/settings").json()
            cfg["preferencias"]["convocacoesCanalAlerta"] = "telegram"
            assert client.put("/api/settings", json=cfg).json()["preferencias"]["convocacoesCanalAlerta"] == "telegram"
    finally:
        config.get_settings.cache_clear()


def test_telegram_token_invalido_mostra_erro_sem_vazar_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "999:SEGREDO")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    config.get_settings.cache_clear()
    try:
        with respx.mock(base_url="https://api.telegram.org") as mock:
            mock.get("/bot999:SEGREDO/getMe").mock(return_value=Response(401, json={"ok": False, "description": "Unauthorized"}))
            st = client.get("/api/settings/telegram")
            assert st.json()["erro"] == "Unauthorized" and "SEGREDO" not in st.text
    finally:
        config.get_settings.cache_clear()
