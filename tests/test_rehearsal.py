# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Rehearsal performers: simulated people standing in for detections."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from openfollow.configuration import AppConfig, CameraConfig, DetectionMaskConfig, GridConfig
from openfollow.runtime.rehearsal import (
    MAX_PERFORMERS,
    RehearsalPerformers,
    performer_position,
    performer_track_id,
)
from openfollow.scene.camera import Camera
from openfollow.scene.solver import invert_overlay_distortion, unproject_to_plane

pytestmark = pytest.mark.unit

_W, _H = 1920, 1080


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _app(cfg: AppConfig | None = None, *, resolution: tuple[int, int] = (_W, _H), camera: bool = True) -> Any:
    cfg = cfg or AppConfig()
    return SimpleNamespace(
        _config=cfg,
        _camera=Camera.from_config(cfg.camera) if camera else None,
        _video_receiver=SimpleNamespace(resolution=resolution),
    )


def _feet_on_floor(app: Any, box: Any) -> tuple[float, float]:
    """Where the pin would put this box's feet: the same undistort + unproject it runs."""
    cam = app._config.camera
    params = np.array([cam.pos_x, cam.pos_y, cam.pos_z, cam.pitch, cam.yaw, cam.roll, cam.fov])
    pt = np.array([[(box.x1 + box.x2) / 2.0 * _W, box.y2 * _H]])
    pt = invert_overlay_distortion(pt, float(_W), float(_H), cam.lens_k1, cam.lens_k2)
    world = unproject_to_plane(params, pt, float(_W), float(_H), app._config.grid.z_offset)
    return float(world[0, 0]), float(world[0, 1])


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def test_paths_stay_inside_the_grid() -> None:
    grid = GridConfig(width=10.0, depth=6.0, x_offset=1.0, y_offset=3.0)
    for index in range(MAX_PERFORMERS):
        for step in range(600):
            pos = performer_position(index, step * 0.5, grid)
            if pos is None:
                continue
            assert -4.0 <= pos[0] <= 6.0
            assert 0.0 <= pos[1] <= 6.0


def test_performers_walk_at_a_human_pace() -> None:
    grid = GridConfig()
    for index in range(MAX_PERFORMERS):
        for step in range(300):
            a = performer_position(index, step * 0.2, grid)
            b = performer_position(index, step * 0.2 + 0.1, grid)
            if a is not None and b is not None:
                assert np.hypot(b[0] - a[0], b[1] - a[1]) / 0.1 < 2.5


def test_each_performer_steps_off_once_a_cycle_and_returns_as_a_new_track() -> None:
    grid = GridConfig()
    for index in range(MAX_PERFORMERS):
        times = np.arange(0.0, 60.0, 0.25)
        off = [t for t in times if performer_position(index, float(t), grid) is None]
        # Three seconds off in every thirty.
        assert len(off) == pytest.approx(2 * 3.0 / 0.25, abs=2)
        tracks = {performer_track_id(index, float(t)) for t in times if performer_position(index, float(t), grid)}
        assert len(tracks) in (2, 3)


def test_performers_leave_at_different_times() -> None:
    grid = GridConfig()
    first_exit = [
        next(t for t in np.arange(0.0, 30.0, 0.1) if performer_position(i, float(t), grid) is None)
        for i in range(MAX_PERFORMERS)
    ]
    assert len({round(t) for t in first_exit}) == MAX_PERFORMERS


def test_track_ids_never_collide_between_performers() -> None:
    ids = {performer_track_id(i, t) for i in range(MAX_PERFORMERS) for t in (0.0, 100.0, 10_000.0)}
    assert len(ids) == MAX_PERFORMERS * 3
    assert min(ids) >= 0


# ---------------------------------------------------------------------------
# Boxes
# ---------------------------------------------------------------------------


def _performers(clock: _Clock | None = None) -> RehearsalPerformers:
    return RehearsalPerformers(clock=clock or _Clock())


@pytest.mark.parametrize("lens", [(0.0, 0.0), (-0.12, 0.03)], ids=["pinhole", "distorted"])
def test_box_feet_land_where_the_performer_stands(lens: tuple[float, float]) -> None:
    cfg = AppConfig()
    cfg.camera = CameraConfig(lens_k1=lens[0], lens_k2=lens[1])
    app = _app(cfg)
    clock = _Clock()
    performers = _performers(clock)
    clock.now += 7.0
    performers.update(app, 3)

    assert len(performers.detections) == 3
    for box in performers.detections:
        index = box.track_id // 100_000
        expected = performer_position(index, 7.0, cfg.grid)
        assert expected is not None
        assert _feet_on_floor(app, box) == pytest.approx(expected, abs=1e-3)
        assert 0.0 < box.y1 < box.y2 <= 1.0
        assert box.confidence >= performers.confidence_threshold
        assert box.age_s == 0.0


def test_a_performer_off_stage_has_no_box() -> None:
    clock = _Clock()
    performers = _performers(clock)
    # Performer 0 is off for the first three seconds of each cycle.
    clock.now += 1.0
    performers.update(_app(), 1)
    assert performers.detections == []
    clock.now += 5.0
    performers.update(_app(), 1)
    assert len(performers.detections) == 1


def test_count_is_capped_at_the_maximum() -> None:
    clock = _Clock()
    performers = _performers(clock)
    clock.now += 4.0
    performers.update(_app(), 20)
    assert len(performers.detections) <= MAX_PERFORMERS
    assert len({b.track_id for b in performers.detections}) == len(performers.detections)


@pytest.mark.parametrize(
    "app",
    [
        pytest.param(_app(resolution=(0, 0)), id="no-picture"),
        pytest.param(_app(camera=False), id="no-camera"),
        pytest.param(SimpleNamespace(_config=AppConfig(), _camera=None, _video_receiver=None), id="no-receiver"),
    ],
)
def test_nothing_to_project_into_gives_no_boxes(app: Any) -> None:
    performers = _performers()
    performers.detections = ["stale"]  # type: ignore[list-item]
    performers.update(app, 3)
    assert performers.detections == []


def test_zero_performers_clears_the_boxes() -> None:
    clock = _Clock()
    performers = _performers(clock)
    clock.now += 5.0
    performers.update(_app(), 2)
    assert performers.detections
    performers.update(_app(), 0)
    assert performers.detections == []


def test_performers_behind_the_camera_are_skipped() -> None:
    cfg = AppConfig()
    # Camera on the stage, looking downstage, away from the grid.
    cfg.camera = CameraConfig(pos_y=3.0, yaw=180.0, pitch=-10.0)
    clock = _Clock()
    performers = _performers(clock)
    clock.now += 5.0
    performers.update(_app(cfg), 6)
    for box in performers.detections:
        assert box.y2 > box.y1


def test_a_picture_upside_down_gives_no_boxes() -> None:
    # A rolled-over camera puts every head below its feet: no upright box fits.
    cfg = AppConfig()
    cfg.camera = CameraConfig(roll=180.0)
    clock = _Clock()
    performers = _performers(clock)
    clock.now += 5.0
    performers.update(_app(cfg), 6)
    assert performers.detections == []


def test_masks_apply_as_they_do_to_real_detections() -> None:
    cfg = AppConfig()
    cfg.detection.masks_enabled = True
    cfg.detection.masks = [DetectionMaskConfig(vertices=[[0.0, 0.0], [0.01, 0.0], [0.01, 0.01]])]
    clock = _Clock()
    performers = _performers(clock)
    clock.now += 5.0
    performers.update(_app(cfg), 3)
    assert performers.detections == []


def test_coast_window_follows_the_grace_period() -> None:
    cfg = AppConfig()
    cfg.detection.grace_period_ms = 1200
    performers = _performers()
    performers.update(_app(cfg), 1)
    assert performers.coast_s == pytest.approx(1.2)


def test_fully_automatic_follows_the_first_performer() -> None:
    clock = _Clock()
    performers = _performers(clock)
    assert performers.tracked_detection is None
    clock.now += 12.0
    performers.update(_app(), 3)
    assert performers.tracked_detection is not None
    assert performers.tracked_detection.track_id == min(b.track_id for b in performers.detections)
    assert performers.available is True


# ---------------------------------------------------------------------------
# Through the All Performers pin
# ---------------------------------------------------------------------------


class _Marker:
    def __init__(self) -> None:
        self.pos = (0.0, 0.0, 1.0)
        self.status = 1.0

    def set_pos(self, x: float, y: float, z: float, *, status: float | None = None) -> None:
        self.pos = (x, y, z)
        if status is not None:
            self.status = status

    def set_status(self, status: float) -> None:
        self.status = status


def test_rehearsal_performers_take_markers_and_drive_them_to_where_they_walk() -> None:
    from openfollow.runtime.services_detection_pin import apply_detection_pin

    cfg = AppConfig()
    cfg.detection.enabled = True
    cfg.detection.pin_mode = "multi"
    cfg.detection.pin_point = "bottom"
    cfg.detection.smoothing = 1.0
    cfg.detection.prediction = 0.0
    markers = {mid: _Marker() for mid in (1, 2, 3)}
    app = _app(cfg)
    app._server = SimpleNamespace(get_marker=markers.get)
    app._controlled_ids = [1, 2, 3]
    app._detection_pin_states = {}
    app._detection_pin_mode = None
    app._assist_manual = {}
    app._selected_id = 1

    clock = _Clock()
    performers = _performers(clock)
    clock.now += 8.0
    performers.update(app, 3)
    apply_detection_pin(
        app,
        person_detector=performers,
        unproject_cam_buffer=np.zeros(7),
        screen_point_buffer=np.zeros((1, 2)),
    )

    walked = sorted(performer_position(i, 8.0, cfg.grid) for i in range(3))  # type: ignore[type-var]
    driven = sorted((m.pos[0], m.pos[1]) for m in markers.values())
    assert np.allclose(driven, walked, atol=1e-3)
    assert all(m.status > 0.5 for m in markers.values())
