# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""OSC show-control input: a desk choosing whom the spotlight follows, and freezing.

Wire format::

    /follow  <markerId:int>   ; follow that performer marker, negative = nobody
    /follow/next              ; next tracked performer
    /follow/prev              ; previous tracked performer
    /follow/none              ; follow nobody
    /freeze  <on>             ; above 0 holds every output, 0 releases
    /freeze/toggle            ; flip the freeze

Handlers run on the listener thread and only queue; the main loop drains the
queue with :meth:`ShowControlOscAdapter.flush` and applies it. Like the
operator-message adapter it only subscribes on the shared service, so the
listener lifecycle (and the sender allowlist) stays with the marker adapter.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from openfollow.osc.operator_message import _coerce_float, _coerce_int
from openfollow.osc.service import OscService

logger = logging.getLogger(__name__)

# Bounds the queue if a sender floods it between two frames.
_MAX_PENDING = 64


@dataclass(frozen=True)
class FollowCommand:
    """Follow ``marker_id`` (negative = nobody), or step by ``step`` when non-zero."""

    marker_id: int = -1
    step: int = 0


@dataclass(frozen=True)
class FreezeCommand:
    """Freeze (True), release (False) or toggle (None) every output."""

    frozen: bool | None = None


class ShowControlOscAdapter:
    """Queues ``/follow`` and ``/freeze`` traffic for the main loop."""

    FOLLOW_ADDR = "/follow"
    NEXT_ADDR = "/follow/next"
    PREV_ADDR = "/follow/prev"
    NONE_ADDR = "/follow/none"
    FREEZE_ADDR = "/freeze"
    FREEZE_TOGGLE_ADDR = "/freeze/toggle"

    def __init__(self, service: OscService) -> None:
        self._service = service
        self._lock = threading.Lock()
        self._pending: list[FollowCommand] = []
        self._freeze_pending: list[FreezeCommand] = []
        self._started = False

    def _handlers(self) -> dict[str, Any]:
        return {
            self.FOLLOW_ADDR: self._handle_follow,
            self.NEXT_ADDR: self._handle_next,
            self.PREV_ADDR: self._handle_prev,
            self.NONE_ADDR: self._handle_none,
            self.FREEZE_ADDR: self._handle_freeze,
            self.FREEZE_TOGGLE_ADDR: self._handle_freeze_toggle,
        }

    def start(self) -> None:
        """Subscribe every handler. Idempotent."""
        if self._started:
            return
        for address, handler in self._handlers().items():
            self._service.subscribe(address, handler)
        self._started = True

    def stop(self) -> None:
        """Unsubscribe every handler. Idempotent. Does not touch the listener."""
        if not self._started:
            return
        for address in self._handlers():
            self._service.unsubscribe(address)
        self._started = False

    def flush(self) -> list[FollowCommand]:
        """Return the queued commands in arrival order and clear the queue."""
        with self._lock:
            commands, self._pending = self._pending, []
        return commands

    def flush_freeze(self) -> list[FreezeCommand]:
        """Return the queued freeze commands in arrival order and clear them."""
        with self._lock:
            commands, self._freeze_pending = self._freeze_pending, []
        return commands

    def _queue(self, command: FollowCommand) -> None:
        with self._lock:
            if len(self._pending) >= _MAX_PENDING:
                self._pending.pop(0)
            self._pending.append(command)

    def _queue_freeze(self, command: FreezeCommand) -> None:
        with self._lock:
            if len(self._freeze_pending) >= _MAX_PENDING:
                self._freeze_pending.pop(0)
            self._freeze_pending.append(command)

    def _handle_follow(self, address: str, *args: Any) -> None:
        marker_id = _coerce_int(args[0]) if args else None
        if marker_id is None:
            logger.debug("OSC %s: expected a marker id, got %r – ignoring", address, args)
            return
        self._queue(FollowCommand(marker_id=max(marker_id, -1)))

    def _handle_next(self, address: str, *args: Any) -> None:
        self._queue(FollowCommand(step=1))

    def _handle_prev(self, address: str, *args: Any) -> None:
        self._queue(FollowCommand(step=-1))

    def _handle_none(self, address: str, *args: Any) -> None:
        self._queue(FollowCommand(marker_id=-1))

    def _handle_freeze(self, address: str, *args: Any) -> None:
        value = _coerce_float(args[0]) if args else None
        if value is None:
            logger.debug("OSC %s: expected 0 or 1, got %r – ignoring", address, args)
            return
        self._queue_freeze(FreezeCommand(frozen=value > 0))

    def _handle_freeze_toggle(self, address: str, *args: Any) -> None:
        self._queue_freeze(FreezeCommand())
