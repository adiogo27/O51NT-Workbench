"""Unidades do serviço de autenticação: hashes, e-mail (SMTP simulado), isenção local e canal de entrega."""

from __future__ import annotations

import smtplib

import pytest

from app import config
from app.middleware_auth import acesso_local_direto
from app.models.auth import Usuario
from app.services import auth as svc


def test_hash_com_pepper_persistido(data_dir) -> None:  # noqa: ANN001
    h1 = svc.hash_segredo("123456")
    assert h1 != svc.hash_segredo("123457") and len(h1) == 64
    arq = data_dir / "auth_secret"
    assert arq.exists() and (arq.stat().st_mode & 0o777) == 0o600
    svc.reset_cache()
    assert svc.hash_segredo("123456") == h1  # mesmo pepper após reiniciar


def test_gerar_codigo_e_normalizar_email() -> None:
    c = svc.gerar_codigo()
    assert len(c) == 6 and c.isdigit()
    assert svc.normalizar_email("  Fulano@PRF.gov.br ") == "fulano@prf.gov.br"
    for ruim in ("", "sem", "@x", "x@", "a b@c"):
        with pytest.raises(svc.AuthErro):
            svc.normalizar_email(ruim)


def test_acesso_local_direto() -> None:
    assert acesso_local_direto({"client": ("127.0.0.1", 1), "headers": []})
    assert acesso_local_direto({"client": ("::1", 1), "headers": [(b"host", b"x")]})
    assert not acesso_local_direto({"client": ("127.0.0.1", 1), "headers": [(b"x-forwarded-for", b"1.2.3.4")]})
    assert not acesso_local_direto({"client": ("10.0.0.5", 1), "headers": []})
    assert not acesso_local_direto({"client": None, "headers": []})


def test_canal_de_entrega(data_dir, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    u = Usuario(email="a@b.c", telegram_chat_id="1")
    assert svc.canal_de_entrega(u) == "journal"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:x")
    config.get_settings.cache_clear()
    assert svc.canal_de_entrega(u) == "telegram" and svc.canal_de_entrega(Usuario(email="z@b.c")) == "journal"
    monkeypatch.setenv("SMTP_HOST", "smtp.exemplo.com")
    monkeypatch.setenv("SMTP_USER", "bot@exemplo.com")
    config.get_settings.cache_clear()
    assert svc.canal_de_entrega(u) == "email"
    config.get_settings.cache_clear()


def test_enviar_email_starttls(data_dir, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_USER", "bot@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-pass")
    config.get_settings.cache_clear()
    chamadas: list[str] = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):  # noqa: ANN001
            chamadas.append(f"connect {host}:{port}")

        def __enter__(self):
            return self

        def __exit__(self, *a):  # noqa: ANN002
            chamadas.append("quit")

        def ehlo(self):
            chamadas.append("ehlo")

        def starttls(self, context):  # noqa: ANN001
            chamadas.append("starttls")

        def login(self, u, p):  # noqa: ANN001
            chamadas.append(f"login {u}")

        def send_message(self, msg):  # noqa: ANN001
            chamadas.append(f"send {msg['To']} | {msg['Subject']} | {msg.get_content().splitlines()[0]}")

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    try:
        svc.enviar_email("x@y.z", "O51NT — código de acesso", svc._texto_codigo("123456", "1.2.3.4"))
    finally:
        config.get_settings.cache_clear()
    assert chamadas[0] == "connect smtp.gmail.com:587" and "starttls" in chamadas and "login bot@gmail.com" in chamadas
    assert any(c.startswith("send x@y.z | O51NT — código de acesso | Seu código de acesso ao O51NT Workbench: 123456") for c in chamadas)


def test_enviar_email_sem_smtp_falha(data_dir) -> None:  # noqa: ANN001
    with pytest.raises(RuntimeError):
        svc.enviar_email("x@y.z", "a", "b")
