# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Moving lights over grandMA2 Telnet: the commands, the session and the output's MA2 path."""

from __future__ import annotations

import pytest

from openfollow.configuration import DmxOutputConfig, MovingLightConfig
from openfollow.dmx import ma2
from openfollow.dmx.server import MA2_MAX_FPS, DmxOutputServer, ma2_commands, ma2_degrees
from openfollow.psn.marker import Marker
from openfollow.web.diagnostics import redact_config_secrets

pytestmark = pytest.mark.unit


class _Conn:
    def __init__(self) -> None:
        self.sent = b""
        self.inbox: list[bytes] = [b"Welcome\r\n"]
        self.closed = False
        self.fail_send = False
        self.fail_close = False
        self.blocking: bool | None = None

    def setblocking(self, flag: bool) -> None:
        self.blocking = flag

    def sendall(self, data: bytes) -> None:
        if self.fail_send:
            raise BrokenPipeError("broken pipe")
        self.sent += data

    def recv(self, _n: int) -> bytes:
        if not self.inbox:
            raise BlockingIOError
        return self.inbox.pop(0)

    def close(self) -> None:
        self.closed = True
        if self.fail_close:
            raise OSError("already reset")


class _Connector:
    def __init__(self) -> None:
        self.conns: list[_Conn] = []
        self.addresses: list[tuple[str, int]] = []
        self.refuse = False

    def __call__(self, address: tuple[str, int], timeout: float) -> _Conn:
        self.addresses.append(address)
        if self.refuse:
            raise ConnectionRefusedError("refused")
        conn = _Conn()
        self.conns.append(conn)
        return conn


def _lines(conn: _Conn) -> list[str]:
    return [line for line in conn.sent.decode().split("\r\n") if line]


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def test_aim_command() -> None:
    assert ma2.aim_command(101, 12.5, -40) == 'Fixture 101 ; Attribute "Pan" At 12.50 ; Attribute "Tilt" At -40.00'


def test_login_command_drops_quotes_the_console_cannot_escape() -> None:
    assert ma2.login_command('fo"llow', "pa ss") == 'Login "follow" "pa ss"'


def test_ma2_degrees_are_from_the_centre_of_travel_in_the_channels_direction() -> None:
    light = MovingLightConfig(pan_range=540, tilt_range=270)
    assert ma2_degrees(light, (0.5, 0.5)) == (0.0, 0.0)
    assert ma2_degrees(light, (1.0, 0.0)) == (270.0, -135.0)


def test_ma2_commands_send_only_lights_that_moved_and_have_a_fixture_id() -> None:
    a = MovingLightConfig(id="a", ma2_fixture=101)
    b = MovingLightConfig(id="b", ma2_fixture=0)
    cfg = DmxOutputConfig(protocol="ma2", fixtures=[a, b])
    sent: dict[str, tuple[float, float]] = {}
    assert ma2_commands(cfg, [(a, (0.5, 0.5)), (b, (0.5, 0.5))], sent) == [ma2.aim_command(101, 0.0, 0.0)]
    assert list(sent) == ["a"]
    # A change under the step is not worth a command.
    assert ma2_commands(cfg, [(a, (0.5 + 0.01 / 540, 0.5))], sent) == []
    assert len(ma2_commands(cfg, [(a, (0.51, 0.5))], sent)) == 1


# --------------------------------------------------------------------------- #
# Session
# --------------------------------------------------------------------------- #


def test_the_session_logs_in_then_sends() -> None:
    connector = _Connector()
    session = ma2.Ma2Session("198.51.100.4", 30000, "follow", "pw", clock=lambda: 0.0, connect=connector)
    assert not session.connected
    assert session.send(["Fixture 1"])
    conn = connector.conns[0]
    assert connector.addresses == [("198.51.100.4", 30000)]
    assert conn.blocking is False
    assert _lines(conn) == ['Login "follow" "pw"', "Fixture 1"]
    assert conn.inbox == []  # the echo was read
    session.close()
    assert conn.closed and not session.connected


def test_closing_a_session_the_console_already_dropped_still_forgets_it() -> None:
    connector = _Connector()
    session = ma2.Ma2Session("198.51.100.4", 30000, "u", "", clock=lambda: 0.0, connect=connector)
    assert session.send(["Fixture 1"])
    connector.conns[0].fail_close = True
    session.close()
    assert not session.connected
    session.close()


def test_a_refused_connection_waits_before_trying_again(caplog: pytest.LogCaptureFixture) -> None:
    now = [100.0]
    connector = _Connector()
    connector.refuse = True
    session = ma2.Ma2Session("198.51.100.4", 30000, "u", "", clock=lambda: now[0], connect=connector)
    assert not session.send(["x"])
    assert not session.send(["x"])
    assert len(connector.addresses) == 1
    now[0] += 5.0
    assert not session.send(["x"])
    assert len(connector.addresses) == 2
    assert caplog.text.count("grandMA2 Telnet to 198.51.100.4:30000 failed") == 1
    connector.refuse = False
    now[0] += 5.0
    assert session.send(["x"])


def test_a_dropped_connection_is_reopened() -> None:
    now = [0.0]
    connector = _Connector()
    session = ma2.Ma2Session("h", 1, "u", "", clock=lambda: now[0], connect=connector)
    assert session.send(["one"])
    connector.conns[0].fail_send = True
    assert not session.send(["two"])
    assert connector.conns[0].closed
    now[0] += 5.0
    assert session.send(["three"])
    assert _lines(connector.conns[1]) == ['Login "u" ""', "three"]


def test_a_console_that_hangs_up_is_noticed() -> None:
    connector = _Connector()
    session = ma2.Ma2Session("h", 1, "u", "", clock=lambda: 0.0, connect=connector)
    session.send(["one"])
    connector.conns[0].inbox = [b""]
    assert not session.send(["two"])
    assert not session.connected


# --------------------------------------------------------------------------- #
# Output server
# --------------------------------------------------------------------------- #


class _Clock:
    us = 10_000_000

    def __call__(self) -> int:
        return self.us


def _server(connector: _Connector, marker: Marker | None, now: list[float]) -> DmxOutputServer:
    cfg = DmxOutputConfig(
        enabled=True,
        protocol="ma2",
        host="198.51.100.4",
        ma2_user="follow",
        fixtures=[MovingLightConfig(id="spot", marker_id=1, ma2_fixture=201)],
    )
    return DmxOutputServer(
        cfg,
        lambda _mid: marker,
        socket_factory=lambda: pytest.fail("no UDP socket for grandMA2"),
        clock=lambda: now[0],
        ma2_connect=connector,
    )


def _started(server: DmxOutputServer) -> DmxOutputServer:
    # Sends are driven by hand: the send thread does nothing.
    server._loop = lambda stop: None  # type: ignore[method-assign]
    server.start()
    return server


def _fixture_lines(connector: _Connector) -> list[str]:
    return [line for c in connector.conns for line in _lines(c) if line.startswith("Fixture")]


def test_the_output_sends_a_light_once_until_it_moves() -> None:
    marker = Marker(1, "T", clock=_Clock())
    marker.set_pos(2.0, 3.0, 0.0)
    connector = _Connector()
    server = _started(_server(connector, marker, [0.0]))
    try:
        server.send_once()
        server.send_once()
        assert _lines(connector.conns[0])[0] == 'Login "follow" ""'
        assert len(_fixture_lines(connector)) == 1
        assert _fixture_lines(connector)[0].startswith("Fixture 201 ; ")
        marker.set_pos(-2.0, 3.0, 0.0)
        server.send_once()
        assert len(_fixture_lines(connector)) == 2
    finally:
        server.stop()
    assert connector.conns[0].closed


def test_after_a_reconnect_every_light_is_sent_again() -> None:
    marker = Marker(1, "T", clock=_Clock())
    marker.set_pos(2.0, 3.0, 0.0)
    connector, now = _Connector(), [0.0]
    server = _started(_server(connector, marker, now))
    try:
        server.send_once()
        connector.conns[0].fail_send = True
        marker.set_pos(0.0, 3.0, 0.0)
        server.send_once()  # finds the drop
        now[0] += 5.0
        marker.set_pos(2.0, 3.0, 0.0)  # back where the console last heard
        server.send_once()
        assert len(connector.conns) == 2
        assert _lines(connector.conns[1])[1].startswith("Fixture 201")
    finally:
        server.stop()


def test_a_hand_aim_reaches_the_console() -> None:
    connector = _Connector()
    server = _started(_server(connector, None, [0.0]))
    try:
        server.aim("spot", (0.5, 1.0))
        server.send_once()
        assert _fixture_lines(connector) == [ma2.aim_command(201, 0.0, 135.0)]
    finally:
        server.stop()


def test_the_grandma2_rate_is_capped() -> None:
    assert MA2_MAX_FPS == 15


def test_send_once_before_start_sends_nothing() -> None:
    connector = _Connector()
    _server(connector, None, [0.0]).send_once()
    assert connector.addresses == []


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("field", "raw", "expected"),
    [
        ("ma2_port", 0, 1),
        ("ma2_port", "telnet", 30000),
        ("ma2_user", "  follow ", "follow"),
        ("ma2_user", None, ""),
        ("ma2_password", " p w ", " p w "),
        ("ma2_password", 42, ""),
        ("protocol", "ma2", "ma2"),
    ],
)
def test_ma2_settings_coerce(field: str, raw: object, expected: object) -> None:
    assert getattr(DmxOutputConfig(**{field: raw}), field) == expected


@pytest.mark.parametrize(("raw", "expected"), [(101, 101), (-1, 0), ("x", 0), (200000, 99999), (None, 0)])
def test_ma2_fixture_id_coerces(raw: object, expected: int) -> None:
    assert MovingLightConfig(ma2_fixture=raw).ma2_fixture == expected


def test_the_ma2_password_is_redacted_in_the_diagnostics_bundle() -> None:
    text = '[dmx_output]\nma2_user = "follow"\nma2_password = "hunter2"\n'
    redacted = redact_config_secrets(text)
    assert "hunter2" not in redacted
    assert 'ma2_password = "***"' in redacted
