# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Moving lights: pan / tilt aiming, the calibration fit, DMX packets and the output server."""

from __future__ import annotations

import math
import socket
import struct
import time
from types import SimpleNamespace

import numpy as np
import pytest

from openfollow.configuration import AppConfig, DmxOutputConfig, MovingLightConfig, load_config, save_config
from openfollow.dmx import packets
from openfollow.dmx.server import DmxOutputServer, build_frame, fixture_pose, fixture_travel, universe_in_range
from openfollow.psn.marker import Marker
from openfollow.scene.pan_tilt import (
    CalibrationMark,
    FixturePose,
    Travel,
    aim_angles,
    beam_direction,
    fractions_for,
    solve_pose,
    to_dmx,
)

pytestmark = pytest.mark.unit


def _hits(pose: FixturePose, pan: float, tilt: float, target: tuple[float, float, float]) -> bool:
    beam = beam_direction(pose, pan, tilt)
    v = np.array(target) - np.array([pose.x, pose.y, pose.z])
    return bool(np.allclose(beam, v / np.linalg.norm(v), atol=1e-9))


# --------------------------------------------------------------------------- #
# Aiming
# --------------------------------------------------------------------------- #


def test_a_hung_light_at_tilt_zero_points_straight_down() -> None:
    assert np.allclose(beam_direction(FixturePose(0, 0, 6), 0, 0), [0, 0, -1])


def test_a_floor_light_at_tilt_zero_points_straight_up() -> None:
    assert np.allclose(beam_direction(FixturePose(0, 0, 0, mounting="floor"), 0, 0), [0, 0, 1])


@pytest.mark.parametrize(("heading", "expected"), [(0.0, [0, 1, 0]), (90.0, [1, 0, 0]), (180.0, [0, -1, 0])])
def test_heading_is_the_stage_bearing_of_pan_zero(heading: float, expected: list[float]) -> None:
    pose = FixturePose(0, 0, 6, heading=heading)
    assert np.allclose(beam_direction(pose, 0, 90), expected, atol=1e-12)


@pytest.mark.parametrize("mounting", ["hung", "floor"])
@pytest.mark.parametrize("target", [(2.0, 3.0, 0.0), (-4.0, 1.0, 0.0), (0.5, -2.0, 1.5)])
def test_aim_angles_point_the_beam_at_the_target(mounting: str, target: tuple[float, float, float]) -> None:
    pose = FixturePose(1, 2, 6 if mounting == "hung" else -1, heading=30, pitch=4, roll=-3, mounting=mounting)
    angles = aim_angles(pose, target)
    assert angles is not None
    assert _hits(pose, *angles, target)


def test_aim_angles_at_the_fixture_itself_is_none() -> None:
    assert aim_angles(FixturePose(1, 1, 1), (1, 1, 1)) is None


def test_aim_angles_on_the_pan_axis_pick_pan_zero() -> None:
    assert aim_angles(FixturePose(0, 0, 6), (0, 0, 0)) == (0.0, 0.0)


def test_fractions_for_lands_the_beam_on_the_target() -> None:
    pose, travel = FixturePose(0, 0, 6, heading=20), Travel(540, 270)
    fractions = fractions_for(pose, travel, (3, 2, 0))
    assert fractions is not None
    assert _hits(pose, *travel.to_degrees(*fractions), (3, 2, 0))


def test_fractions_for_follows_the_nearest_solution_instead_of_swinging_round() -> None:
    pose, travel = FixturePose(0, 0, 6), Travel(540, 270)
    previous = fractions_for(pose, travel, (3, 0.01, 0))
    assert previous is not None
    # Crossing behind the pan axis: the light keeps turning the short way.
    after = fractions_for(pose, travel, (3, -0.01, 0), previous)
    assert after is not None
    assert abs(after[0] - previous[0]) < 0.01
    assert abs(after[1] - previous[1]) < 0.01


def test_fractions_for_a_target_at_the_fixture_is_none() -> None:
    assert fractions_for(FixturePose(1.0, 2.0, 6.0), Travel(), (1.0, 2.0, 6.0)) is None


def test_fractions_for_beyond_the_tilt_travel_is_none() -> None:
    # A hung light with 60 degrees of tilt cannot reach a point level with it.
    assert fractions_for(FixturePose(0, 0, 6), Travel(540, 60), (10, 0, 6)) is None


def test_fractions_for_straight_down_keeps_the_previous_pan() -> None:
    travel = Travel(540, 270)
    fractions = fractions_for(FixturePose(0, 0, 6), travel, (0, 0, 0), (0.7, 0.6))
    assert fractions is not None
    assert fractions[0] == pytest.approx(0.7)
    assert fractions[1] == pytest.approx(0.5)


@pytest.mark.parametrize(("invert_pan", "invert_tilt"), [(False, False), (True, False), (False, True), (True, True)])
def test_travel_fractions_and_degrees_round_trip(invert_pan: bool, invert_tilt: bool) -> None:
    travel = Travel(540, 270, invert_pan, invert_tilt)
    assert travel.to_degrees(*travel.to_fractions(100, -40)) == pytest.approx((100, -40))
    assert travel.to_fractions(0, 0) == (0.5, 0.5)


def test_inverting_pan_mirrors_its_fraction() -> None:
    assert Travel(540, 270, invert_pan=True).to_fractions(135, 0)[0] == pytest.approx(0.25)
    assert Travel(540, 270).to_fractions(135, 0)[0] == pytest.approx(0.75)


@pytest.mark.parametrize(
    ("fraction", "fine", "expected"),
    [
        (0.0, False, (0,)),
        (1.0, False, (255,)),
        (0.5, False, (128,)),
        (0.5, True, (128, 0)),
        (1.0, True, (255, 255)),
        (-1.0, True, (0, 0)),
        (2.0, False, (255,)),
    ],
)
def test_to_dmx(fraction: float, fine: bool, expected: tuple[int, ...]) -> None:
    assert to_dmx(fraction, fine) == expected


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #


def _marks_for(pose: FixturePose, travel: Travel, points: list[tuple[float, float, float]]) -> list[CalibrationMark]:
    marks = []
    for point in points:
        fractions = fractions_for(pose, travel, point)
        assert fractions is not None
        marks.append(CalibrationMark(*point, *fractions))
    return marks


_FLOOR_MARKS = [(-4.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 6.0, 0.0), (-4.0, 6.0, 0.0), (0.0, 3.0, 0.0)]


@pytest.mark.parametrize("count", [4, 5])
def test_solve_pose_recovers_where_the_light_hangs(count: int) -> None:
    travel = Travel(540, 270)
    truth = FixturePose(1.5, -2.0, 7.0, heading=25.0, pitch=3.0, roll=-2.0)
    marks = _marks_for(truth, travel, _FLOOR_MARKS[:count])
    result = solve_pose(marks, travel, FixturePose(0, 0, 6))
    assert result is not None
    assert (result.pose.x, result.pose.y, result.pose.z) == pytest.approx((1.5, -2.0, 7.0), abs=1e-3)
    assert result.worst_deg < 0.01
    # The fitted pose aims each mark where it was recorded.
    for mark in marks:
        assert fractions_for(result.pose, travel, (mark.x, mark.y, mark.z)) == pytest.approx(
            (mark.pan, mark.tilt), abs=1e-4
        )


def test_solve_pose_reports_a_mark_recorded_against_the_wrong_point() -> None:
    travel = Travel(540, 270)
    truth = FixturePose(0.0, -1.0, 6.0, heading=10.0)
    marks = _marks_for(truth, travel, _FLOOR_MARKS)
    marks[2] = CalibrationMark(marks[2].x, marks[2].y, 0.0, marks[0].pan, marks[0].tilt)
    result = solve_pose(marks, travel, FixturePose(0, 0, 6))
    assert result is not None
    assert result.worst_deg > 1.0
    assert len(result.errors_deg) == len(marks)


def test_solve_pose_needs_four_marks() -> None:
    # Three marks fit some pose exactly, so they cannot show a wrong one.
    travel = Travel(540, 270)
    marks = _marks_for(FixturePose(0, 0, 6), travel, _FLOOR_MARKS[:3])
    assert solve_pose(marks, travel, FixturePose(0, 0, 6)) is None


def test_solve_pose_from_a_position_that_is_not_a_number_is_none() -> None:
    travel = Travel(540, 270)
    marks = _marks_for(FixturePose(0, 0, 6), travel, _FLOOR_MARKS)
    assert solve_pose(marks, travel, FixturePose(math.nan, 0, 6)) is None


def test_solve_pose_gives_up_when_the_step_cannot_be_solved(monkeypatch: pytest.MonkeyPatch) -> None:
    travel = Travel(540, 270)
    marks = _marks_for(FixturePose(0, 0, 6), travel, _FLOOR_MARKS)

    def _singular(*_args: object) -> None:
        raise np.linalg.LinAlgError("singular")

    monkeypatch.setattr(np.linalg, "solve", _singular)
    assert solve_pose(marks, travel, FixturePose(0, 0, 6)) is None


def test_solve_pose_with_no_iterations_reports_the_starting_pose() -> None:
    travel = Travel(540, 270)
    marks = _marks_for(FixturePose(1.0, 0, 6), travel, _FLOOR_MARKS)
    result = solve_pose(marks, travel, FixturePose(0, 0, 6), iterations=0)
    assert result is not None
    assert (result.pose.x, result.pose.y, result.pose.z) == (0.0, 0.0, 6.0)
    assert result.worst_deg > 0.0


def test_solve_pose_keeps_the_mounting_and_wraps_the_heading() -> None:
    travel = Travel(540, 270)
    truth = FixturePose(0.0, 8.0, 0.5, heading=170.0, mounting="floor")
    marks = _marks_for(truth, travel, _FLOOR_MARKS)
    result = solve_pose(marks, travel, FixturePose(0, 7, 0, heading=160, mounting="floor"))
    assert result is not None
    assert result.pose.mounting == "floor"
    assert -180.0 <= result.pose.heading < 180.0
    assert result.worst_deg < 0.01


# --------------------------------------------------------------------------- #
# Packets
# --------------------------------------------------------------------------- #


def test_artnet_dmx_layout() -> None:
    data = bytes(range(10))
    pkt = packets.artnet_dmx(0x0123, data, sequence=7)
    assert pkt[:8] == b"Art-Net\x00"
    assert struct.unpack("<H", pkt[8:10])[0] == 0x5000
    assert struct.unpack(">H", pkt[10:12])[0] == 14
    assert pkt[12] == 7  # sequence
    assert pkt[13] == 0  # physical
    assert pkt[14] == 0x23  # sub-net / universe
    assert pkt[15] == 0x01  # net
    assert struct.unpack(">H", pkt[16:18])[0] == 10
    assert pkt[18:] == data


@pytest.mark.parametrize(("length", "padded"), [(0, 2), (1, 2), (3, 4), (512, 512)])
def test_artnet_dmx_pads_to_an_even_length_of_at_least_two(length: int, padded: int) -> None:
    pkt = packets.artnet_dmx(0, b"\x01" * length)
    assert struct.unpack(">H", pkt[16:18])[0] == padded
    assert len(pkt) == 18 + padded


@pytest.mark.parametrize("universe", [-1, 32768])
def test_artnet_dmx_refuses_a_universe_out_of_range(universe: int) -> None:
    with pytest.raises(ValueError, match="universe"):
        packets.artnet_dmx(universe, b"")


def test_a_universe_holds_512_slots() -> None:
    with pytest.raises(ValueError, match="512"):
        packets.artnet_dmx(0, b"\x00" * 513)


def test_sacn_packet_layout() -> None:
    cid = bytes(range(16))
    data = bytes(512)
    pkt = packets.sacn_packet(258, data, cid=cid, source_name="Station", sequence=9, priority=150)
    assert len(pkt) == 638
    assert pkt[4:16] == b"ASC-E1.17\x00\x00\x00"
    assert struct.unpack(">H", pkt[16:18])[0] == 0x7000 | (638 - 16)
    assert struct.unpack(">I", pkt[18:22])[0] == 4
    assert pkt[22:38] == cid
    assert struct.unpack(">H", pkt[38:40])[0] == 0x7000 | (638 - 38)
    assert struct.unpack(">I", pkt[40:44])[0] == 2
    assert pkt[44:108].rstrip(b"\x00") == b"Station"
    assert pkt[108] == 150  # priority
    assert pkt[111] == 9  # sequence
    assert struct.unpack(">H", pkt[113:115])[0] == 258
    assert struct.unpack(">H", pkt[115:117])[0] == 0x7000 | (638 - 115)
    assert pkt[117] == 0x02
    assert pkt[118] == 0xA1
    assert struct.unpack(">H", pkt[123:125])[0] == 513
    assert pkt[125] == packets.START_CODE_DMX
    assert pkt[126:] == data


def test_sacn_per_address_priority_carries_its_start_code() -> None:
    pkt = packets.sacn_packet(1, b"\x96\x00", cid=bytes(16), source_name="", sequence=1, start_code=0xDD)
    assert pkt[125] == 0xDD
    assert pkt[126:] == b"\x96\x00"


def test_sacn_source_name_is_cut_to_63_bytes_and_null_terminated() -> None:
    pkt = packets.sacn_packet(1, b"", cid=bytes(16), source_name="x" * 100, sequence=0)
    assert pkt[44:107] == b"x" * 63
    assert pkt[107] == 0


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"universe": 0}, "universe"),
        ({"universe": 64000}, "universe"),
        ({"cid": b"short"}, "CID"),
        ({"priority": 201}, "priority"),
    ],
)
def test_sacn_packet_refuses_bad_arguments(kwargs: dict, match: str) -> None:
    args = {"universe": 1, "data": b"", "cid": bytes(16), "source_name": "", "sequence": 0} | kwargs
    with pytest.raises(ValueError, match=match):
        packets.sacn_packet(**args)


@pytest.mark.parametrize(("universe", "group"), [(1, "239.255.0.1"), (258, "239.255.1.2"), (63999, "239.255.249.255")])
def test_sacn_multicast_group(universe: int, group: str) -> None:
    assert packets.sacn_multicast_group(universe) == group


def test_new_cid_is_sixteen_random_bytes() -> None:
    assert len(packets.new_cid()) == 16
    assert packets.new_cid() != packets.new_cid()


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #


def test_moving_light_defaults() -> None:
    light = MovingLightConfig()
    assert light.id
    assert light.channels() == (0, 2)
    assert (light.mounting, light.fine, light.pan_range, light.tilt_range) == ("hung", True, 540.0, 270.0)


@pytest.mark.parametrize(
    ("field", "raw", "expected"),
    [
        ("universe", "abc", 1),
        ("universe", None, 1),
        ("universe", 70000, 63999),
        ("address", 0, 1),
        ("address", 900, 512),
        ("pan_channel", True, 1),
        ("pan_range", "wide", 540.0),
        ("tilt_range", 0, 1.0),
        ("pos_z", 5000, 1000.0),
        ("heading", 400, 360.0),
        ("base_pitch", 90, 45.0),
        ("marker_id", -3, 0),
        ("fine", "yes", True),
        ("name", "  Spot  ", "Spot"),
        ("name", None, ""),
    ],
)
def test_moving_light_coerces_bad_values(field: str, raw: object, expected: object) -> None:
    light = MovingLightConfig(**{field: raw})
    assert getattr(light, field) == expected


@pytest.mark.parametrize("raw", ["truss", "", None, 3])
def test_moving_light_rejects_an_unknown_mounting(raw: object) -> None:
    assert MovingLightConfig(mounting=raw).mounting == "hung"


def test_moving_light_channels_count_from_its_address() -> None:
    assert MovingLightConfig(address=101, pan_channel=1, tilt_channel=3).channels() == (100, 102)


@pytest.mark.parametrize(
    ("field", "raw", "expected"),
    [
        ("protocol", "dmx512", "sacn"),
        ("protocol", None, "sacn"),
        ("fps", 0, 1),
        ("fps", 100, 44),
        ("fps", "fast", 30),
        ("priority", 0, 1),
        ("priority", 255, 200),
        ("host", "  10.0.0.5 ", "10.0.0.5"),
        ("host", None, ""),
        ("enabled", "maybe", False),
    ],
)
def test_dmx_output_coerces_bad_values(field: str, raw: object, expected: object) -> None:
    assert getattr(DmxOutputConfig(**{field: raw}), field) == expected


def test_dmx_output_drops_entries_that_are_not_lights_and_renumbers_duplicate_ids() -> None:
    cfg = DmxOutputConfig(fixtures=[{"id": "a", "name": "One"}, "junk", 3, {"id": "a", "name": "Two"}])
    assert [f.name for f in cfg.fixtures] == ["One", "Two"]
    assert cfg.fixtures[0].id == "a"
    assert cfg.fixtures[1].id != "a"
    assert cfg.fixture("a") is cfg.fixtures[0]
    assert cfg.fixture("missing") is None


def test_dmx_output_ignores_unknown_fixture_keys() -> None:
    cfg = DmxOutputConfig(fixtures=[{"id": "a", "colour": "red"}])
    assert cfg.fixtures[0].id == "a"


def test_dmx_output_round_trips_through_toml(tmp_path) -> None:
    path = tmp_path / "config.toml"
    cfg = AppConfig()
    cfg.dmx_output = DmxOutputConfig(
        enabled=True,
        protocol="artnet",
        host="10.0.0.9",
        fixtures=[MovingLightConfig(id="spot", name="Spot", universe=3, address=40, heading=45.0, mounting="floor")],
    )
    save_config(cfg, str(path))
    loaded = load_config(str(path)).dmx_output
    assert (loaded.enabled, loaded.protocol, loaded.host) == (True, "artnet", "10.0.0.9")
    light = loaded.fixture("spot")
    assert light is not None
    assert (light.name, light.universe, light.address, light.heading, light.mounting) == (
        "Spot",
        3,
        40,
        45.0,
        "floor",
    )


# --------------------------------------------------------------------------- #
# Output server
# --------------------------------------------------------------------------- #


class _Clock:
    def __init__(self) -> None:
        self.us = 10_000_000

    def __call__(self) -> int:
        return self.us


def _marker(clock: _Clock, pos: tuple[float, float, float] = (2.0, 3.0, 0.0), marker_id: int = 1) -> Marker:
    marker = Marker(marker_id, "T", clock=clock)
    marker.set_pos(*pos)
    return marker


def _cfg(**light: object) -> DmxOutputConfig:
    fields = {"id": "spot", "marker_id": 1, "universe": 2, "address": 11} | light
    return DmxOutputConfig(enabled=True, fixtures=[MovingLightConfig(**fields)])


class _FakeSocket:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False
        self.fail = False

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.fail:
            raise OSError("network is unreachable")
        self.sent.append((data, addr))

    def close(self) -> None:
        self.closed = True


def test_build_frame_writes_the_fixtures_pan_and_tilt() -> None:
    clock = _Clock()
    marker = _marker(clock)
    cfg = _cfg()
    last: dict[str, tuple[float, float]] = {}
    frame = build_frame(cfg, lambda _mid: marker, last, {}, now_us=clock.us)
    light = cfg.fixtures[0]
    expected = fractions_for(fixture_pose(light), fixture_travel(light), marker.pos)
    assert expected is not None
    assert last["spot"] == expected
    data = frame.data[2]
    assert tuple(data[10:12]) == to_dmx(expected[0], True)
    assert tuple(data[12:14]) == to_dmx(expected[1], True)
    assert list(frame.owned[2][10:14]) == [1, 1, 1, 1]
    assert sum(frame.owned[2]) == 4


def test_build_frame_holds_a_light_whose_marker_went_stale() -> None:
    clock = _Clock()
    marker = _marker(clock)
    cfg = _cfg()
    last: dict[str, tuple[float, float]] = {}
    build_frame(cfg, lambda _mid: marker, last, {}, now_us=clock.us)
    held = last["spot"]
    clock.us += 5_000_000
    frame = build_frame(cfg, lambda _mid: marker, last, {}, now_us=clock.us)
    assert last["spot"] == held
    assert tuple(frame.data[2][10:12]) == to_dmx(held[0], True)


def test_build_frame_sends_nothing_for_a_light_that_never_had_a_position() -> None:
    frame = build_frame(_cfg(), lambda _mid: None, {}, {})
    assert frame.data == {}


def test_build_frame_follows_a_hand_aim_over_the_marker() -> None:
    clock = _Clock()
    frame = build_frame(_cfg(fine=False), lambda _mid: _marker(clock), {}, {"spot": (0.25, 1.0)}, now_us=clock.us)
    assert frame.data[2][10] == to_dmx(0.25, False)[0]
    assert frame.data[2][12] == 255


@pytest.mark.parametrize("light", [{"enabled": False}, {"universe": 0}])
def test_build_frame_skips_a_light_that_is_off_or_on_a_universe_the_protocol_lacks(light: dict) -> None:
    clock = _Clock()
    assert build_frame(_cfg(**light), lambda _mid: _marker(clock), {}, {}, now_us=clock.us).data == {}


@pytest.mark.parametrize(
    ("protocol", "universe", "ok"),
    [("sacn", 0, False), ("sacn", 1, True), ("artnet", 0, True), ("artnet", 32768, False), ("sacn", 63999, True)],
)
def test_universe_in_range(protocol: str, universe: int, ok: bool) -> None:
    assert universe_in_range(protocol, universe) is ok


def test_build_frame_drops_channels_past_the_end_of_the_universe() -> None:
    clock = _Clock()
    frame = build_frame(
        _cfg(address=512, pan_channel=1, tilt_channel=1), lambda _mid: _marker(clock), {}, {}, now_us=clock.us
    )
    assert sum(frame.owned[2]) == 1


def _server(cfg: DmxOutputConfig, marker: Marker | None, sock: _FakeSocket, now: list[float]) -> DmxOutputServer:
    return DmxOutputServer(
        cfg, lambda _mid: marker, source_name="Station", socket_factory=lambda: sock, clock=lambda: now[0]
    )


def test_sacn_sends_data_and_once_a_second_the_per_address_priority() -> None:
    clock = _Clock()
    sock, now = _FakeSocket(), [100.0]
    server = _server(_cfg(), _marker(clock), sock, now)
    server._sock = sock
    server.send_once()
    assert [(pkt[125], addr) for pkt, addr in sock.sent] == [
        (0x00, ("239.255.0.2", packets.SACN_PORT)),
        (0xDD, ("239.255.0.2", packets.SACN_PORT)),
    ]
    priority = sock.sent[1][0][126:]
    assert list(priority[10:14]) == [150] * 4
    assert sum(priority) == 600
    sock.sent.clear()
    now[0] += 0.5
    server.send_once()
    assert [pkt[125] for pkt, _ in sock.sent] == [0x00]
    sock.sent.clear()
    now[0] += 0.6
    server.send_once()
    assert [pkt[125] for pkt, _ in sock.sent] == [0x00, 0xDD]


def test_sacn_sequence_counts_per_universe_and_start_code() -> None:
    clock = _Clock()
    sock, now = _FakeSocket(), [100.0]
    server = _server(_cfg(), _marker(clock), sock, now)
    server._sock = sock
    server.send_once()
    server.send_once()
    assert [pkt[111] for pkt, _ in sock.sent] == [1, 1, 2]


def test_sacn_to_a_named_host_sends_unicast() -> None:
    clock = _Clock()
    cfg = _cfg()
    cfg.host = "10.0.0.7"
    sock = _FakeSocket()
    server = _server(cfg, _marker(clock), sock, [0.0])
    server._sock = sock
    server.send_once()
    assert {addr for _, addr in sock.sent} == {("10.0.0.7", packets.SACN_PORT)}


@pytest.mark.parametrize(("host", "target"), [("", "255.255.255.255"), ("10.0.0.8", "10.0.0.8")])
def test_artnet_sends_one_dmx_packet_per_universe(host: str, target: str) -> None:
    clock = _Clock()
    cfg = _cfg()
    cfg.protocol, cfg.host = "artnet", host
    sock = _FakeSocket()
    server = _server(cfg, _marker(clock), sock, [0.0])
    server._sock = sock
    server.send_once()
    assert len(sock.sent) == 1
    pkt, addr = sock.sent[0]
    assert addr == (target, packets.ARTNET_PORT)
    assert pkt[:8] == b"Art-Net\x00"
    assert pkt[12] == 1


def test_a_failed_send_is_logged_once_until_a_send_succeeds(caplog: pytest.LogCaptureFixture) -> None:
    clock = _Clock()
    sock = _FakeSocket()
    server = _server(_cfg(), _marker(clock), sock, [0.0])
    server._sock = sock
    sock.fail = True
    server.send_once()
    server.send_once()
    assert caplog.text.count("could not send") == 1
    sock.fail = False
    server.send_once()
    sock.fail = True
    server.send_once()
    assert caplog.text.count("could not send") == 2


def test_aim_clamps_and_release_hands_back_to_the_marker() -> None:
    clock = _Clock()
    sock = _FakeSocket()
    server = _server(_cfg(), _marker(clock), sock, [0.0])
    server.aim("spot", (1.5, -0.2))
    assert server.current("spot") == (1.0, 0.0)
    server.aim("spot", None)
    assert server.current("spot") is None


def test_start_runs_the_send_thread_and_stop_closes_the_socket() -> None:
    clock = _Clock()
    sock = _FakeSocket()
    cfg = _cfg()
    cfg.fps = 44
    server = _server(cfg, _marker(clock), sock, [0.0])
    server.start()
    try:
        assert server.running
        server.start()  # already running: no second thread
        for _ in range(200):
            if sock.sent:
                break
            time.sleep(0.01)
        assert sock.sent
    finally:
        server.stop()
    assert not server.running
    assert sock.closed


def test_stopping_a_server_that_never_started_does_nothing() -> None:
    sock = _FakeSocket()
    server = _server(_cfg(), None, sock, [0.0])
    server.stop()
    assert not server.running
    assert not sock.closed


def test_restart_forgets_lights_that_were_removed() -> None:
    clock = _Clock()
    sock = _FakeSocket()
    server = _server(_cfg(), _marker(clock), sock, [0.0])
    server._sock = sock
    server.send_once()
    server.aim("spot", (0.5, 0.5))
    assert server.current("spot") is not None
    server.restart(DmxOutputConfig(enabled=True, fixtures=[MovingLightConfig(id="other")]))
    try:
        assert server.current("spot") is None
    finally:
        server.stop()


def test_send_once_without_a_socket_sends_nothing() -> None:
    clock = _Clock()
    server = _server(_cfg(), _marker(clock), _FakeSocket(), [0.0])
    server.send_once()  # never started: nothing to send through


def test_the_default_socket_can_broadcast() -> None:
    sock = DmxOutputServer._open_socket()
    try:
        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST)
    finally:
        sock.close()


# --------------------------------------------------------------------------- #
# Lifecycle in services
# --------------------------------------------------------------------------- #


def _services(cfg: AppConfig):
    from openfollow.services import AppRuntimeServices

    services = AppRuntimeServices.__new__(AppRuntimeServices)
    services._app = SimpleNamespace(_config=cfg, _dmx_server=None, _server=None)
    return services


class _FakeDmxServer:
    def __init__(self, cfg, markers, *, source_name: str) -> None:
        self.cfg, self.source_name = cfg, source_name
        self.started = self.stopped = 0
        self.restarted: list = []
        self.aims: list = []

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1

    def restart(self, cfg) -> None:
        self.restarted.append(cfg)

    def aim(self, fixture_id, fractions) -> None:
        self.aims.append((fixture_id, fractions))


def test_moving_lights_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    import openfollow.services as services_module

    monkeypatch.setattr(services_module, "DmxOutputServer", _FakeDmxServer)
    cfg = AppConfig(psn_system_name="Stage Left")
    services = _services(cfg)

    services.init_dmx_output()
    assert services._app._dmx_server is None  # off: nothing starts
    assert services._aim_moving_light("spot", (0.5, 0.5)) is False

    # The dispatcher installs the new section before it calls the live apply.
    cfg.dmx_output = DmxOutputConfig(enabled=True)
    services.apply_dmx_output_change(cfg.dmx_output)
    server = services._app._dmx_server
    assert server is not None and server.started == 1
    assert server.source_name == "Stage Left"

    on_again = DmxOutputConfig(enabled=True, fps=20)
    services.apply_dmx_output_change(on_again)
    assert server.restarted == [on_again]

    assert services._aim_moving_light("spot", (0.1, 0.2)) is True
    assert server.aims == [("spot", (0.1, 0.2))]

    services.apply_dmx_output_change(DmxOutputConfig(enabled=False))
    assert server.stopped == 1
    assert services._app._dmx_server is None

    services.apply_dmx_output_change(DmxOutputConfig(enabled=False))
    assert services._app._dmx_server is None


def test_angle_math_stays_finite_at_the_horizon() -> None:
    pose = FixturePose(0, 0, 6)
    angles = aim_angles(pose, (10, 0, 6))
    assert angles is not None
    assert angles[1] == pytest.approx(90.0)
    assert all(math.isfinite(a) for a in angles)
