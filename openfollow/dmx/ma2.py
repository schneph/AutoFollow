# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""grandMA2 Telnet: pan / tilt as command-line commands, for a desk that cannot merge DMX.

The console's Telnet remote takes the same command line as its keyboard, so
each light becomes ``Fixture N ; Attribute "Pan" At p ; Attribute "Tilt" At t``
in the logged-in user's programmer. Attribute values are degrees from the
centre of the fixture's travel, matching how the desk shows pan and tilt.
"""

from __future__ import annotations

import logging
import socket
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

MA2_DEFAULT_PORT = 30000
# Smallest change in degrees worth a command; below it the beam does not visibly move.
MIN_STEP_DEG = 0.05
_CONNECT_TIMEOUT_S = 2.0
_RETRY_AFTER_S = 5.0


def quote(text: str) -> str:
    """A command-line string argument: the console has no escape, so a quote is dropped."""
    return '"' + text.replace('"', "") + '"'


def login_command(user: str, password: str) -> str:
    return f"Login {quote(user)} {quote(password)}"


def aim_command(fixture: int, pan_deg: float, tilt_deg: float) -> str:
    return f'Fixture {fixture} ; Attribute "Pan" At {pan_deg:.2f} ; Attribute "Tilt" At {tilt_deg:.2f}'


class Ma2Session:
    """One Telnet connection to the console: logs in on connect, reconnects after a failure.

    Never raises from :meth:`send`; a failed connection is retried no sooner
    than every few seconds so an unreachable console costs nothing per frame.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        *,
        clock: Callable[[], float],
        connect: Callable[[tuple[str, int], float], Any] | None = None,
    ) -> None:
        self._address = (host, port)
        self._login = login_command(user, password)
        self._clock = clock
        self._connect = connect or socket.create_connection
        self._sock: Any = None
        self._retry_at = 0.0
        self._warned = False

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def send(self, commands: list[str]) -> bool:
        """Send ``commands``, connecting first if needed. False when nothing reached the console."""
        if self._sock is None and not self._open():
            return False
        try:
            self._sock.sendall("".join(f"{c}\r\n" for c in commands).encode("utf-8"))
            self._drain()
        except OSError as exc:
            self._fail(exc)
            return False
        self._warned = False
        return True

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _open(self) -> bool:
        now = self._clock()
        if now < self._retry_at:
            return False
        try:
            sock = self._connect(self._address, _CONNECT_TIMEOUT_S)
            sock.setblocking(False)
            sock.sendall(f"{self._login}\r\n".encode())
        except OSError as exc:
            self._fail(exc)
            return False
        self._sock = sock
        logger.info("grandMA2 Telnet connected to %s:%d", *self._address)
        return True

    def _drain(self) -> None:
        # The console echoes every command; reading it keeps its send buffer from filling.
        while True:
            try:
                data = self._sock.recv(4096)
            except BlockingIOError:
                return
            if not data:
                raise ConnectionResetError("the console closed the connection")

    def _fail(self, exc: OSError) -> None:
        self.close()
        self._retry_at = self._clock() + _RETRY_AFTER_S
        if not self._warned:
            logger.warning("grandMA2 Telnet to %s:%d failed: %s", *self._address, exc)
            self._warned = True
