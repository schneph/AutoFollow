# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""OSC show-control input: a desk choosing whom the spotlight follows.

Wire format::

    /follow  <markerId:int>   ; follow that performer marker, negative = nobody
    /follow/next              ; next tracked performer
    /follow/prev              ; previous tracked performer
    /follow/none              ; follow nobody

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

from openfollow.osc.operator_message import _coerce_int
from openfollow.osc.service import OscService

logger = logging.getLogger(__name__)

# Bounds the queue if a sender floods it between two frames.
_MAX_PENDING = 64


@dataclass(frozen=True)
class FollowCommand:
    """Follow ``marker_id`` (negative = nobody), or step by ``step`` when non-zero."""

    marker_id: int = -1
    step: int = 0


class ShowControlOscAdapter:
    """Queues ``/follow`` traffic for the main loop."""

    FOLLOW_ADDR = "/follow"
    NEXT_ADDR = "/follow/next"
    PREV_ADDR = "/follow/prev"
    NONE_ADDR = "/follow/none"

    def __init__(self, service: OscService) -> None:
        self._service = service
        self._lock = threading.Lock()
        self._pending: list[FollowCommand] = []
        self._started = False

    def _handlers(self) -> dict[str, Any]:
        return {
            self.FOLLOW_ADDR: self._handle_follow,
            self.NEXT_ADDR: self._handle_next,
            self.PREV_ADDR: self._handle_prev,
            self.NONE_ADDR: self._handle_none,
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

    def _queue(self, command: FollowCommand) -> None:
        with self._lock:
            if len(self._pending) >= _MAX_PENDING:
                self._pending.pop(0)
            self._pending.append(command)

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
