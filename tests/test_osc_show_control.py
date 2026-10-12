# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Unit tests for the OSC show-control (``/follow``) adapter."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from openfollow.osc.input import OscMarkerAdapter
from openfollow.osc.service import _PYTHONOSC_AVAILABLE, OscService
from openfollow.osc.show_control import FollowCommand, FreezeCommand, ShowControlOscAdapter
from tests._ports import bind_free_udp_port

pytestmark = pytest.mark.unit

_ADDRESSES = {"/follow", "/follow/next", "/follow/prev", "/follow/none", "/freeze", "/freeze/toggle"}


class _FakeService:
    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}
        self.subscribe_calls: list[str] = []
        self.unsubscribe_calls: list[str] = []

    def subscribe(self, pattern: str, handler: Any) -> None:
        self.subscribe_calls.append(pattern)
        self.handlers[pattern] = handler

    def unsubscribe(self, pattern: str) -> None:
        self.unsubscribe_calls.append(pattern)
        self.handlers.pop(pattern, None)

    def send(self, address: str, *args: Any) -> None:
        self.handlers[address](address, *args)


def _wire() -> tuple[ShowControlOscAdapter, _FakeService]:
    svc = _FakeService()
    adapter = ShowControlOscAdapter(svc)  # type: ignore[arg-type]
    adapter.start()
    return adapter, svc


def test_start_subscribes_every_address_once() -> None:
    adapter, svc = _wire()
    adapter.start()
    assert sorted(svc.subscribe_calls) == sorted(_ADDRESSES)


def test_stop_unsubscribes_every_address_and_is_idempotent() -> None:
    adapter, svc = _wire()
    adapter.stop()
    adapter.stop()
    assert sorted(svc.unsubscribe_calls) == sorted(_ADDRESSES)
    assert svc.handlers == {}


@pytest.mark.parametrize(
    "arg,expected",
    [(2, 2), (2.0, 2), ("2", 2), (" 4.0 ", 4), (0, 0), (-1, -1), (-9, -1)],
    ids=["int", "float", "string", "padded-float-string", "zero", "minus-one", "below-minus-one"],
)
def test_follow_queues_the_marker_id(arg: Any, expected: int) -> None:
    adapter, svc = _wire()
    svc.send("/follow", arg)
    assert adapter.flush() == [FollowCommand(marker_id=expected)]


@pytest.mark.parametrize("args", [(), ("abc",), (True,), (float("nan"),), (None,)])
def test_follow_without_a_usable_id_is_dropped(args: tuple[Any, ...]) -> None:
    adapter, svc = _wire()
    svc.send("/follow", *args)
    assert adapter.flush() == []


@pytest.mark.parametrize(
    "address,expected",
    [
        ("/follow/next", FollowCommand(step=1)),
        ("/follow/prev", FollowCommand(step=-1)),
        ("/follow/none", FollowCommand()),
    ],
)
def test_step_and_none_ignore_their_arguments(address: str, expected: FollowCommand) -> None:
    adapter, svc = _wire()
    svc.send(address)
    svc.send(address, 1.0)
    assert adapter.flush() == [expected, expected]


def test_flush_returns_arrival_order_and_clears() -> None:
    adapter, svc = _wire()
    svc.send("/follow", 3)
    svc.send("/follow/next")
    svc.send("/follow/none")
    assert adapter.flush() == [FollowCommand(marker_id=3), FollowCommand(step=1), FollowCommand()]
    assert adapter.flush() == []


def test_a_flood_keeps_only_the_newest_commands() -> None:
    adapter, svc = _wire()
    for marker_id in range(100):
        svc.send("/follow", marker_id)
    commands = adapter.flush()
    assert len(commands) == 64
    assert commands[-1] == FollowCommand(marker_id=99)
    assert commands[0] == FollowCommand(marker_id=36)


def test_commands_from_several_threads_are_all_queued() -> None:
    adapter, svc = _wire()
    threads = [threading.Thread(target=svc.send, args=("/follow/next",)) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert adapter.flush() == [FollowCommand(step=1)] * 20


@pytest.mark.parametrize(
    "arg,frozen",
    [(1, True), (1.0, True), (0.5, True), ("1", True), (0, False), (0.0, False), ("0", False), (-1, False)],
)
def test_freeze_reads_above_zero_as_hold(arg: Any, frozen: bool) -> None:
    adapter, svc = _wire()
    svc.send("/freeze", arg)
    assert adapter.flush_freeze() == [FreezeCommand(frozen=frozen)]
    assert adapter.flush() == []


@pytest.mark.parametrize("args", [(), ("abc",), (True,), (float("inf"),)])
def test_freeze_without_a_usable_value_is_dropped(args: tuple[Any, ...]) -> None:
    adapter, svc = _wire()
    svc.send("/freeze", *args)
    assert adapter.flush_freeze() == []


def test_freeze_toggle_queues_a_toggle_and_floods_keep_the_newest() -> None:
    adapter, svc = _wire()
    svc.send("/freeze/toggle")
    assert adapter.flush_freeze() == [FreezeCommand()]
    for _ in range(70):
        svc.send("/freeze/toggle")
    svc.send("/freeze", 1)
    commands = adapter.flush_freeze()
    assert len(commands) == 64
    assert commands[-1] == FreezeCommand(frozen=True)
    assert adapter.flush_freeze() == []


@pytest.mark.integration
@pytest.mark.skipif(not _PYTHONOSC_AVAILABLE, reason="python-osc not installed")
def test_real_udp_follow_cues_reach_the_queue() -> None:
    """A desk's ``/follow`` cue arrives over UDP on the marker listener."""
    svc = OscService()
    built: list[OscMarkerAdapter] = []

    def _start(port: int) -> None:
        listener = OscMarkerAdapter(svc, port=port, allowed_sender_ips=["127.0.0.1"])
        listener.start()
        built.append(listener)

    port = bind_free_udp_port(_start)
    adapter = ShowControlOscAdapter(svc)
    adapter.start()
    try:
        svc.send("/follow", [4], host="127.0.0.1", port=port)
        svc.send("/follow/prev", [], host="127.0.0.1", port=port)
        deadline = time.monotonic() + 1.0
        commands: list[FollowCommand] = []
        while time.monotonic() < deadline and len(commands) < 2:
            commands += adapter.flush()
            time.sleep(0.01)
        assert commands == [FollowCommand(marker_id=4), FollowCommand(step=-1)]
    finally:
        adapter.stop()
        built[-1].stop()
        svc.shutdown()
