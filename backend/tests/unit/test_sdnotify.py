from __future__ import annotations

import asyncio
import os
import socket
from pathlib import Path

import pytest

from app import sdnotify

pytestmark = pytest.mark.unit


def test_sem_notify_socket_e_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    monkeypatch.delenv("WATCHDOG_USEC", raising=False)
    assert sdnotify.notify("READY=1") is False
    assert sdnotify.intervalo_watchdog() is None
    assert sdnotify.iniciar_watchdog() is None


def test_envia_para_socket_unix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    caminho = tmp_path / "notify.sock"
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(str(caminho))
    srv.settimeout(2)
    monkeypatch.setenv("NOTIFY_SOCKET", str(caminho))
    try:
        assert sdnotify.notify("READY=1") is True
        assert srv.recv(64) == b"READY=1"
    finally:
        srv.close()


def test_socket_inexistente_nao_levanta(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NOTIFY_SOCKET", str(tmp_path / "nao-existe.sock"))
    assert sdnotify.notify("WATCHDOG=1") is False


def test_intervalo_watchdog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATCHDOG_USEC", "60000000")
    monkeypatch.setenv("WATCHDOG_PID", str(os.getpid()))
    assert sdnotify.intervalo_watchdog() == 30.0
    monkeypatch.setenv("WATCHDOG_PID", str(os.getpid() + 1))
    assert sdnotify.intervalo_watchdog() is None
    monkeypatch.delenv("WATCHDOG_PID")
    monkeypatch.setenv("WATCHDOG_USEC", "abc")
    assert sdnotify.intervalo_watchdog() is None


async def test_loop_watchdog_envia_heartbeats(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    caminho = tmp_path / "wd.sock"
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(str(caminho))
    srv.setblocking(False)
    monkeypatch.setenv("NOTIFY_SOCKET", str(caminho))
    monkeypatch.setenv("WATCHDOG_USEC", "100000")  # 0,1 s → heartbeat a cada 0,05 s
    monkeypatch.delenv("WATCHDOG_PID", raising=False)
    tarefa = sdnotify.iniciar_watchdog()
    assert tarefa is not None
    try:
        await asyncio.sleep(0.3)
        recebidos = []
        while True:
            try:
                recebidos.append(srv.recv(64))
            except BlockingIOError:
                break
        assert len(recebidos) >= 2 and set(recebidos) == {b"WATCHDOG=1"}
    finally:
        tarefa.cancel()
        srv.close()
