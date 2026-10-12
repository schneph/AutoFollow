# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""OSC cue addresses for lighting desks, ready to drop into a trigger zone."""

from __future__ import annotations

import math
import re

# MagicQ's OSC playback numbers start at 1; cue numbers may carry a decimal (2.5).
MAGICQ_MAX_PLAYBACK = 999
_CUE_RE = re.compile(r"^\d{1,4}(\.\d{1,3})?$")


class PresetError(ValueError):
    """An argument the desk would not accept; the message is shown to the operator."""


def magicq_zone_cues(playback: object, cue: object = "") -> dict[str, str]:
    """Zone addresses that run a MagicQ playback while the zone is occupied.

    The first person in goes the playback (or jumps it to ``cue``); the last
    one out releases it. Raises :class:`PresetError` for a playback or cue
    MagicQ would not accept.
    """
    try:
        number = float(str(playback).strip())
    except ValueError:
        number = math.nan
    if not number.is_integer() or not 1 <= number <= MAGICQ_MAX_PLAYBACK:
        raise PresetError(f"Playback must be a whole number from 1 to {MAGICQ_MAX_PLAYBACK}.")
    pb = int(number)
    cue_text = str(cue).strip()
    if cue_text and (not _CUE_RE.match(cue_text) or float(cue_text) <= 0):
        raise PresetError("Cue must be a number above 0, such as 3 or 2.5.")
    return {
        "osc_address_first_entry": f"/pb/{pb}/{cue_text}" if cue_text else f"/pb/{pb}/go",
        "osc_address_final_exit": f"/pb/{pb}/release",
    }
