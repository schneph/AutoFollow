# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Moving-light output: aims each configured fixture at its marker and sends pan / tilt.

The send thread works out every fixture's pan / tilt from its marker each
frame and writes them into that fixture's universe. A marker that is missing
or stale holds the light where it last pointed, since a light has no way to
say "unknown" and swinging to a default would sweep the stage. Over sACN a
per-address priority packet claims only the pan / tilt channels, so a
receiver that merges by priority takes everything else from the desk. A
grandMA2 is driven over Telnet instead, one command per light that moved.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from openfollow.dmx.ma2 import MIN_STEP_DEG, Ma2Session, aim_command
from openfollow.dmx.packets import (
    ARTNET_MAX_UNIVERSE,
    ARTNET_PORT,
    SACN_MAX_UNIVERSE,
    SACN_MIN_UNIVERSE,
    SACN_PORT,
    START_CODE_PRIORITY,
    UNIVERSE_SIZE,
    artnet_dmx,
    new_cid,
    sacn_multicast_group,
    sacn_packet,
)
from openfollow.psn.marker import is_marker_stale
from openfollow.scene.pan_tilt import FixturePose, Travel, fractions_for, to_dmx

if TYPE_CHECKING:
    from openfollow.configuration import DmxOutputConfig, MovingLightConfig
    from openfollow.psn.marker import Marker

logger = logging.getLogger(__name__)

MarkerLookup = Callable[[int], "Marker | None"]
# How often sACN per-address priority is repeated, as E1.31 receivers expect about once a second.
_PRIORITY_INTERVAL_S = 1.0
_BROADCAST = "255.255.255.255"
# The console runs every Telnet command through its command line; faster floods its queue.
MA2_MAX_FPS = 15


def fixture_pose(fixture: MovingLightConfig) -> FixturePose:
    return FixturePose(
        fixture.pos_x,
        fixture.pos_y,
        fixture.pos_z,
        fixture.heading,
        fixture.base_pitch,
        fixture.base_roll,
        fixture.mounting,
    )


def fixture_travel(fixture: MovingLightConfig) -> Travel:
    return Travel(fixture.pan_range, fixture.tilt_range, fixture.invert_pan, fixture.invert_tilt)


def universe_in_range(protocol: str, universe: int) -> bool:
    if protocol == "artnet":
        return 0 <= universe <= ARTNET_MAX_UNIVERSE
    return SACN_MIN_UNIVERSE <= universe <= SACN_MAX_UNIVERSE


@dataclass
class Frame:
    """One send's worth of universes: the slot values and which slots this station owns."""

    data: dict[int, bytearray] = field(default_factory=dict)
    owned: dict[int, bytearray] = field(default_factory=dict)

    def write(self, universe: int, slot: int, values: tuple[int, ...]) -> None:
        data = self.data.setdefault(universe, bytearray(UNIVERSE_SIZE))
        owned = self.owned.setdefault(universe, bytearray(UNIVERSE_SIZE))
        for offset, value in enumerate(values):
            if 0 <= slot + offset < UNIVERSE_SIZE:
                data[slot + offset] = value
                owned[slot + offset] = 1


def aim_fixtures(
    cfg: DmxOutputConfig,
    markers: MarkerLookup,
    last: dict[str, tuple[float, float]],
    aims: dict[str, tuple[float, float]],
    *,
    now_us: int | None = None,
) -> list[tuple[MovingLightConfig, tuple[float, float]]]:
    """Every enabled fixture with the pan / tilt fractions it now points at, updating ``last``.

    ``aims`` holds fixtures pointed by hand (while calibrating); they ignore
    their marker. A fixture whose marker is missing or stale repeats ``last``,
    and one that has never had a position is left out.
    """
    out = []
    for fixture in cfg.fixtures:
        if not fixture.enabled:
            continue
        fractions = aims.get(fixture.id)
        if fractions is None:
            marker = markers(fixture.marker_id)
            previous = last.get(fixture.id)
            if marker is not None and not is_marker_stale(marker, now_us=now_us):
                fractions = fractions_for(fixture_pose(fixture), fixture_travel(fixture), marker.pos, previous)
            if fractions is None:
                fractions = previous
        if fractions is None:
            continue
        last[fixture.id] = fractions
        out.append((fixture, fractions))
    return out


def build_frame(
    cfg: DmxOutputConfig,
    markers: MarkerLookup,
    last: dict[str, tuple[float, float]],
    aims: dict[str, tuple[float, float]],
    *,
    now_us: int | None = None,
) -> Frame:
    """The universes carrying every aimed fixture's pan / tilt (see :func:`aim_fixtures`)."""
    frame = Frame()
    for fixture, fractions in aim_fixtures(cfg, markers, last, aims, now_us=now_us):
        if not universe_in_range(cfg.protocol, fixture.universe):
            continue
        pan_slot, tilt_slot = fixture.channels()
        frame.write(fixture.universe, pan_slot, to_dmx(fractions[0], fixture.fine))
        frame.write(fixture.universe, tilt_slot, to_dmx(fractions[1], fixture.fine))
    return frame


def ma2_degrees(fixture: MovingLightConfig, fractions: tuple[float, float]) -> tuple[float, float]:
    """Pan / tilt as the console shows them: degrees from the centre of travel, in the channel's direction."""
    return (fractions[0] - 0.5) * fixture.pan_range, (fractions[1] - 0.5) * fixture.tilt_range


def ma2_commands(
    cfg: DmxOutputConfig,
    aimed: list[tuple[MovingLightConfig, tuple[float, float]]],
    sent: dict[str, tuple[float, float]],
) -> list[str]:
    """Commands for the fixtures that moved at least :data:`MIN_STEP_DEG` since ``sent``, updating it."""
    commands = []
    for fixture, fractions in aimed:
        if fixture.ma2_fixture <= 0:
            continue
        pan, tilt = ma2_degrees(fixture, fractions)
        previous = sent.get(fixture.id)
        if previous is not None and max(abs(pan - previous[0]), abs(tilt - previous[1])) < MIN_STEP_DEG:
            continue
        sent[fixture.id] = (pan, tilt)
        commands.append(aim_command(fixture.ma2_fixture, pan, tilt))
    return commands


class DmxOutputServer:
    """Sends the moving lights' pan / tilt at ``cfg.fps`` from its own thread."""

    def __init__(
        self,
        cfg: DmxOutputConfig,
        markers: MarkerLookup,
        *,
        source_name: str = "OpenFollow",
        socket_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        ma2_connect: Callable[[tuple[str, int], float], Any] | None = None,
    ) -> None:
        self._cfg = cfg
        self._markers = markers
        self._source_name = source_name
        self._socket_factory = socket_factory or self._open_socket
        self._clock = clock
        self._cid = new_cid()
        self._lock = threading.Lock()
        self._last: dict[str, tuple[float, float]] = {}
        self._aims: dict[str, tuple[float, float]] = {}
        self._sequence: dict[tuple[int, int], int] = {}
        self._last_priority_s: float | None = None
        self._sock: Any = None
        self._thread: threading.Thread | None = None
        self._stop: threading.Event | None = None
        self._warned_failure = False
        self._ma2: Ma2Session | None = None
        self._ma2_sent: dict[str, tuple[float, float]] = {}
        self._ma2_connect = ma2_connect

    @staticmethod
    def _open_socket() -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        return sock

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        if self._cfg.protocol == "ma2":
            cfg = self._cfg
            self._ma2 = Ma2Session(
                cfg.host, cfg.ma2_port, cfg.ma2_user, cfg.ma2_password, clock=self._clock, connect=self._ma2_connect
            )
            self._ma2_sent = {}
        else:
            self._sock = self._socket_factory()
        stop = threading.Event()
        self._stop = stop
        self._thread = threading.Thread(target=self._loop, args=(stop,), name="dmx-output", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._stop = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        if self._ma2 is not None:
            self._ma2.close()
            self._ma2 = None

    def restart(self, cfg: DmxOutputConfig) -> None:
        self.stop()
        with self._lock:
            self._cfg = cfg
            known = {f.id for f in cfg.fixtures}
            self._last = {k: v for k, v in self._last.items() if k in known}
            self._aims = {k: v for k, v in self._aims.items() if k in known}
        self._last_priority_s = None
        self.start()

    def aim(self, fixture_id: str, fractions: tuple[float, float] | None) -> None:
        """Point a fixture by hand (pan, tilt fractions), or hand it back to its marker with ``None``."""
        with self._lock:
            if fractions is None:
                self._aims.pop(fixture_id, None)
            else:
                self._aims[fixture_id] = (min(max(fractions[0], 0.0), 1.0), min(max(fractions[1], 0.0), 1.0))

    def current(self, fixture_id: str) -> tuple[float, float] | None:
        """The pan / tilt fractions a fixture last pointed at."""
        with self._lock:
            return self._aims.get(fixture_id) or self._last.get(fixture_id)

    def _loop(self, stop: threading.Event) -> None:
        while not stop.is_set():
            started = self._clock()
            self.send_once()
            fps = min(self._cfg.fps, MA2_MAX_FPS) if self._cfg.protocol == "ma2" else self._cfg.fps
            stop.wait(max(0.0, 1.0 / fps - (self._clock() - started)))

    def send_once(self) -> None:
        if self._cfg.protocol == "ma2":
            self._send_ma2()
            return
        with self._lock:
            cfg = self._cfg
            frame = build_frame(cfg, self._markers, self._last, dict(self._aims))
        now = self._clock()
        send_priority = cfg.protocol == "sacn" and (
            self._last_priority_s is None or now - self._last_priority_s >= _PRIORITY_INTERVAL_S
        )
        if send_priority:
            self._last_priority_s = now
        for universe in sorted(frame.data):
            if cfg.protocol == "artnet":
                self._send(
                    artnet_dmx(universe, bytes(frame.data[universe]), self._next(universe, 0) or 1),
                    cfg.host or _BROADCAST,
                    ARTNET_PORT,
                )
                continue
            target = cfg.host or sacn_multicast_group(universe)
            self._send(self._sacn(cfg, universe, bytes(frame.data[universe]), 0x00), target, SACN_PORT)
            if send_priority:
                levels = bytes(cfg.priority if owned else 0 for owned in frame.owned[universe])
                self._send(self._sacn(cfg, universe, levels, START_CODE_PRIORITY), target, SACN_PORT)

    def _send_ma2(self) -> None:
        session = self._ma2
        if session is None:
            return
        with self._lock:
            aimed = aim_fixtures(self._cfg, self._markers, self._last, dict(self._aims))
        if not session.connected:
            # A new connection starts a new programmer: every light is sent again.
            self._ma2_sent = {}
        sent = dict(self._ma2_sent)
        commands = ma2_commands(self._cfg, aimed, sent)
        if commands and session.send(commands):
            self._ma2_sent = sent

    def _sacn(self, cfg: DmxOutputConfig, universe: int, slots: bytes, start_code: int) -> bytes:
        return sacn_packet(
            universe,
            slots,
            cid=self._cid,
            source_name=self._source_name,
            sequence=self._next(universe, start_code),
            priority=cfg.priority,
            start_code=start_code,
        )

    def _next(self, universe: int, stream: int) -> int:
        key = (universe, stream)
        value = (self._sequence.get(key, 0) + 1) % 256
        self._sequence[key] = value
        return value

    def _send(self, data: bytes, host: str, port: int) -> None:
        sock = self._sock
        if sock is None:
            return
        try:
            sock.sendto(data, (host, port))
        except OSError as exc:
            if not self._warned_failure:
                logger.warning("Moving lights output could not send to %s:%d: %s", host, port, exc)
                self._warned_failure = True
            return
        self._warned_failure = False
