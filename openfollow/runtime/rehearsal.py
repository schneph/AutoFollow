# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Rehearsal performers: simulated people walking the stage in place of detections.

Each performer walks a smooth looping path inside the grid and steps off stage
for a few seconds every cycle, coming back as a new track the way a real
detector re-numbers someone who left. Their boxes are projected through the
live camera, so the whole chain after detection (marker assignment,
spotlights, trigger zones, every output) runs as it would with people on stage.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from openfollow.scene.solver import apply_overlay_distortion, project_points
from openfollow.video.detection import DetectionBox, filter_detections_to_masks

MAX_PERFORMERS = 6
PERSON_HEIGHT_M = 1.7
# Box width as a share of its height, roughly a standing person.
_BOX_ASPECT = 0.35
# Share of the grid's half-extent the paths reach, so nobody walks off its edge.
_REACH = 0.8
_CYCLE_S = 30.0
_OFFSTAGE_S = 3.0
_CONFIDENCE = 0.9
# Track ids are ``performer * _TRACK_STRIDE + cycle``: stable within a cycle, new after each exit.
_TRACK_STRIDE = 100_000


def performer_position(index: int, t: float, grid: Any) -> tuple[float, float] | None:
    """Stage position of performer ``index`` at ``t`` seconds, or ``None`` while off stage."""
    phase = index * _CYCLE_S / MAX_PERFORMERS
    if (t + phase) % _CYCLE_S < _OFFSTAGE_S:
        return None
    period = 20.0 + 4.0 * index
    angle = 2.0 * math.pi * t / period + index * 1.1
    x = grid.x_offset + _REACH * grid.width / 2.0 * math.sin(angle)
    y = grid.y_offset + _REACH * grid.depth / 2.0 * math.sin(angle * 1.37 + index * 0.7)
    return x, y


def performer_track_id(index: int, t: float) -> int:
    """The track id performer ``index`` carries at ``t``; it changes each time they step off."""
    phase = index * _CYCLE_S / MAX_PERFORMERS
    return index * _TRACK_STRIDE + int((t + phase) // _CYCLE_S)


class RehearsalPerformers:
    """Stands in for the person detector while rehearsal performers are on.

    Exposes what the pin, the overlay and the zone engine read from the
    detector; :meth:`update` refreshes the boxes once per frame.
    """

    available = True
    confidence_threshold = 0.5

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._start = clock()
        self.detections: list[DetectionBox] = []
        self.coast_s = 0.5

    @property
    def tracked_detection(self) -> DetectionBox | None:
        """Fully Automatic follows the first performer on stage."""
        return min(self.detections, key=lambda b: b.track_id) if self.detections else None

    def update(self, app: Any, count: int) -> None:
        """Project ``count`` performers through the live camera into the current frame."""
        cfg = app._config
        w, h = app._video_receiver.resolution if app._video_receiver is not None else (0, 0)
        if count <= 0 or app._camera is None or w <= 0 or h <= 0:
            self.detections = []
            return
        t = self._clock() - self._start
        cam = app._camera.to_config()
        params = np.array([cam.pos_x, cam.pos_y, cam.pos_z, cam.pitch, cam.yaw, cam.roll, cam.fov], dtype=np.float64)
        floor = float(cfg.grid.z_offset)
        boxes: list[DetectionBox] = []
        for index in range(min(count, MAX_PERFORMERS)):
            pos = performer_position(index, t, cfg.grid)
            if pos is None:
                continue
            world = np.array([[pos[0], pos[1], floor], [pos[0], pos[1], floor + PERSON_HEIGHT_M]])
            screen = apply_overlay_distortion(
                project_points(params, world, float(w), float(h)),
                float(w),
                float(h),
                cfg.camera.lens_k1,
                cfg.camera.lens_k2,
            )
            if not np.all(np.isfinite(screen)):
                continue
            (fx, fy), (_hx, hy) = screen
            if fy <= hy:
                continue
            half_w = _BOX_ASPECT * (fy - hy) / 2.0
            box = DetectionBox(
                x1=(fx - half_w) / w,
                y1=hy / h,
                x2=(fx + half_w) / w,
                y2=fy / h,
                confidence=_CONFIDENCE,
                track_id=performer_track_id(index, t),
            )
            if box.x2 > 0.0 and box.x1 < 1.0 and box.y2 > 0.0 and box.y1 < 1.0:
                boxes.append(box)
        det = cfg.detection
        self.detections = filter_detections_to_masks(boxes, det.masks, masks_enabled=det.masks_enabled)
        self.coast_s = max(0.0, det.grace_period_ms / 1000.0)
