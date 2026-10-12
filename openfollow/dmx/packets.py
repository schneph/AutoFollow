# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Art-Net (ArtDmx) and sACN (ANSI E1.31) packet builders.

Pure functions over one universe's 512 slots. sACN also carries a
per-address priority packet (start code ``0xDD``): it lets a receiver take
just the pan / tilt channels from this station and every other channel from
the desk, where a plain data packet would claim the whole universe.
"""

from __future__ import annotations

import struct
import uuid

UNIVERSE_SIZE = 512

ARTNET_PORT = 6454
ARTNET_MAX_UNIVERSE = 32767
_ARTNET_ID = b"Art-Net\x00"
_ARTNET_OP_DMX = 0x5000
_ARTNET_PROTOCOL = 14

SACN_PORT = 5568
SACN_MIN_UNIVERSE = 1
SACN_MAX_UNIVERSE = 63999
SACN_DEFAULT_PRIORITY = 100
START_CODE_DMX = 0x00
START_CODE_PRIORITY = 0xDD
_SACN_ACN_ID = b"ASC-E1.17\x00\x00\x00"
_SACN_ROOT_VECTOR = 0x00000004
_SACN_FRAMING_VECTOR = 0x00000002
_SACN_DMP_VECTOR = 0x02
_SACN_SOURCE_NAME_BYTES = 64


def _slots(data: bytes) -> bytes:
    if len(data) > UNIVERSE_SIZE:
        raise ValueError(f"a universe holds {UNIVERSE_SIZE} slots, got {len(data)}")
    return data


def artnet_dmx(universe: int, data: bytes, sequence: int = 0) -> bytes:
    """An ArtDmx packet for a 15-bit port address (Net in bits 14-8, Sub-Net / Universe in 7-0).

    ``sequence`` 1..255 lets a receiver reorder packets; 0 switches that off.
    The data length is padded to an even count of at least 2, as the
    specification requires.
    """
    if not 0 <= universe <= ARTNET_MAX_UNIVERSE:
        raise ValueError(f"Art-Net universe must be 0..{ARTNET_MAX_UNIVERSE}, got {universe}")
    payload = _slots(data)
    if len(payload) < 2 or len(payload) % 2:
        payload = payload + b"\x00" * (max(2, len(payload) + len(payload) % 2) - len(payload))
    return (
        _ARTNET_ID
        + struct.pack("<H", _ARTNET_OP_DMX)
        + struct.pack(">H", _ARTNET_PROTOCOL)
        + struct.pack("BBBB", sequence & 0xFF, 0, universe & 0xFF, universe >> 8)
        + struct.pack(">H", len(payload))
        + payload
    )


def sacn_multicast_group(universe: int) -> str:
    """E1.31's multicast address for ``universe``: ``239.255.<hi>.<lo>``."""
    _check_sacn_universe(universe)
    return f"239.255.{universe >> 8}.{universe & 0xFF}"


def _check_sacn_universe(universe: int) -> None:
    if not SACN_MIN_UNIVERSE <= universe <= SACN_MAX_UNIVERSE:
        raise ValueError(f"sACN universe must be {SACN_MIN_UNIVERSE}..{SACN_MAX_UNIVERSE}, got {universe}")


def new_cid() -> bytes:
    """A component identifier: one random UUID per sender, kept for its lifetime."""
    return uuid.uuid4().bytes


def sacn_packet(
    universe: int,
    data: bytes,
    *,
    cid: bytes,
    source_name: str,
    sequence: int,
    priority: int = SACN_DEFAULT_PRIORITY,
    start_code: int = START_CODE_DMX,
) -> bytes:
    """An E1.31 data packet: root layer, framing layer and DMP layer around the slots."""
    _check_sacn_universe(universe)
    if len(cid) != 16:
        raise ValueError("a CID is 16 bytes")
    if not 0 <= priority <= 200:
        raise ValueError(f"sACN priority must be 0..200, got {priority}")
    slots = bytes([start_code]) + _slots(data)
    dmp = struct.pack(">HBBHHH", 0x7000 | (10 + len(slots)), _SACN_DMP_VECTOR, 0xA1, 0, 1, len(slots)) + slots
    name = source_name.encode("utf-8")[: _SACN_SOURCE_NAME_BYTES - 1].ljust(_SACN_SOURCE_NAME_BYTES, b"\x00")
    framing_len = 77 + len(dmp)
    framing = (
        struct.pack(">HI", 0x7000 | framing_len, _SACN_FRAMING_VECTOR)
        + name
        + struct.pack(">BHBBH", priority, 0, sequence & 0xFF, 0, universe)
        + dmp
    )
    root_len = 22 + len(framing)
    return (
        struct.pack(">HH", 0x0010, 0x0000)
        + _SACN_ACN_ID
        + struct.pack(">HI", 0x7000 | root_len, _SACN_ROOT_VECTOR)
        + cid
        + framing
    )
