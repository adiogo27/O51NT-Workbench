"""Integração mínima com o systemd (sd_notify) — sem dependência externa.

Quando o processo roda como serviço `Type=notify`, o systemd exporta NOTIFY_SOCKET. Enviamos:
- READY=1 ao fim do startup;
- WATCHDOG=1 periodicamente (metade de WATCHDOG_USEC), para `WatchdogSec` reiniciar o serviço se travar;
- STOPPING=1 no shutdown.
Fora do systemd (dev, testes, run.sh) tudo vira no-op.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket

logger = logging.getLogger("o51nt.sdnotify")


def notify(estado: str) -> bool:
    """Envia uma mensagem ao NOTIFY_SOCKET. Retorna False se não houver socket (no-op)."""
    caminho = os.environ.get("NOTIFY_SOCKET")
    if not caminho:
        return False
    if caminho.startswith("@"):  # socket abstrato (Linux)
        caminho = "\0" + caminho[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(caminho)
            s.sendall(estado.encode())
        return True
    except OSError as exc:
        logger.warning("sd_notify falhou", extra={"dados": {"estado": estado, "erro": str(exc)}})
        return False


def intervalo_watchdog() -> float | None:
    """Metade de WATCHDOG_USEC em segundos (recomendação do systemd), ou None se desativado."""
    usec = os.environ.get("WATCHDOG_USEC")
    if not usec or not usec.isdigit() or int(usec) <= 0:
        return None
    pid = os.environ.get("WATCHDOG_PID")
    if pid and pid.isdigit() and int(pid) != os.getpid():
        return None  # o watchdog é de outro processo (ex.: wrapper)
    return int(usec) / 1_000_000 / 2


async def _loop_watchdog(intervalo: float) -> None:
    while True:
        await asyncio.sleep(intervalo)
        notify("WATCHDOG=1")


def iniciar_watchdog() -> asyncio.Task[None] | None:
    """Cria a tarefa de heartbeat se o systemd pediu watchdog; senão None."""
    intervalo = intervalo_watchdog()
    if intervalo is None:
        return None
    logger.info("watchdog do systemd ativo", extra={"dados": {"intervalo_s": intervalo}})
    return asyncio.create_task(_loop_watchdog(intervalo), name="sd-watchdog")
