# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Freeze: hold every marker this station controls where it is.

The hold sits on the markers themselves (``Marker.hold``), so PSN, OTP, RTTrPM
and the OSC outputs all keep sending the frozen positions as live, and every
writer (input, detection, OSC jumps) keeps running underneath. Releasing hands
each marker straight back to whatever drives it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openfollow.app import OpenFollowApp

logger = logging.getLogger(__name__)

STATUS_FLAG = "outputs_frozen"
_STATUS_ROW = ("caution", "Outputs frozen: markers held")


def outputs_frozen(app: OpenFollowApp) -> bool:
    """True while the outputs are frozen."""
    return bool(getattr(app, "_outputs_frozen", False))


def set_outputs_frozen(app: OpenFollowApp, frozen: bool | None) -> bool:
    """Freeze (True), release (False) or toggle (None) the outputs.

    Returns True when the state changed. The hold applies to the markers at
    once, and the HUD row and the web UI follow.
    """
    target = not outputs_frozen(app) if frozen is None else bool(frozen)
    if target == outputs_frozen(app):
        return False
    app._outputs_frozen = target
    sync_output_freeze(app)
    logger.info("Outputs %s.", "frozen: every marker held where it is" if target else "released")
    return True


def sync_output_freeze(app: OpenFollowApp) -> None:
    """Make every marker's hold, the HUD row and the web mirror match the freeze state.

    Polled as well as called on a change, so a marker taken under control while
    frozen is held too. One released from control keeps the hold it had; it is
    no longer sent by this station.
    """
    frozen = outputs_frozen(app)
    server = app._server
    if server is not None:
        for marker_id in app._controlled_ids:
            marker = server.get_marker(marker_id)
            if marker is not None:
                marker.hold(frozen)
    app._runtime_services._status_flags[STATUS_FLAG] = _STATUS_ROW if frozen else None
    app._web_commands.publish_outputs_frozen(frozen)


def check_output_freeze(app: OpenFollowApp) -> None:
    """Apply the freeze requests from the web UI and OSC, then keep the holds in sync."""
    requests = list(app._web_commands.consume_freeze_requests())
    if app._input_manager is not None:
        requests += [command.frozen for command in app._input_manager.flush_freeze_commands()]
    for request in requests:
        set_outputs_frozen(app, request)
    sync_output_freeze(app)
