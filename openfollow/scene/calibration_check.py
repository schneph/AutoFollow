# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Measure a saved calibration against the stage's own floor marks.

The setup wizard pins the four grid corners (at the grid's height) and the
centre-stage reference (on the floor at the PSN origin) onto the video. The
check projects those same marks with the saved camera, the operator drags each
one onto the real tape mark, and the drag is unprojected back onto the mark's
plane: the distance from where the mark should be is the calibration's error
at that spot, in metres on the stage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from openfollow.scene.solver import (
    apply_overlay_distortion,
    invert_overlay_distortion,
    project_points,
    unproject_to_plane,
)

# Corner order matches the wizard: downstage-left, downstage-right, upstage-right,
# upstage-left, then the centre-stage reference.
MARK_NAMES = ("DSL", "DSR", "USR", "USL", "REF")

# Error bounds (m) for the three levels: within OK_M the marker lands where the
# light should; up to CAUTION_M it is usable but visibly off; beyond is an error.
OK_M = 0.10
CAUTION_M = 0.30


@dataclass(frozen=True)
class MarkError:
    name: str
    expected: tuple[float, float, float]
    measured: tuple[float, float] | None
    error_m: float | None

    @property
    def level(self) -> str:
        return error_level(self.error_m)


def error_level(error_m: float | None) -> str:
    """``ok`` / ``caution`` / ``error`` for a measured distance; ``error`` when unmeasurable."""
    if error_m is None:
        return "error"
    if error_m <= OK_M:
        return "ok"
    if error_m <= CAUTION_M:
        return "caution"
    return "error"


def camera_params(camera: Any) -> npt.NDArray[np.float64]:
    """The solver's 7-vector from a ``CameraConfig``."""
    return np.array(
        [camera.pos_x, camera.pos_y, camera.pos_z, camera.pitch, camera.yaw, camera.roll, camera.fov],
        dtype=np.float64,
    )


def expected_marks(grid: Any) -> dict[str, tuple[float, float, float]]:
    """World position (PSN-absolute) of every mark the wizard pins."""
    hw, hd = grid.width / 2.0, grid.depth / 2.0
    ox, oy, oz = grid.x_offset, grid.y_offset, grid.z_offset
    # PSN +X is stage left, so the stage-left corners sit at +hw.
    return {
        "DSL": (ox + hw, oy - hd, oz),
        "DSR": (ox - hw, oy - hd, oz),
        "USR": (ox - hw, oy + hd, oz),
        "USL": (ox + hw, oy + hd, oz),
        "REF": (0.0, 0.0, 0.0),
    }


def project_marks(camera: Any, grid: Any, width: float, height: float) -> dict[str, tuple[float, float] | None]:
    """Where the saved calibration draws each mark on a ``width`` x ``height`` image.

    ``None`` for a mark at or behind the camera.
    """
    marks = expected_marks(grid)
    world = np.array([marks[n] for n in MARK_NAMES], dtype=np.float64)
    screen = apply_overlay_distortion(
        project_points(camera_params(camera), world, width, height), width, height, camera.lens_k1, camera.lens_k2
    )
    out: dict[str, tuple[float, float] | None] = {}
    for name, pt in zip(MARK_NAMES, screen, strict=True):
        out[name] = (float(pt[0]), float(pt[1])) if np.isfinite(pt).all() else None
    return out


def measure_marks(
    camera: Any,
    grid: Any,
    screen_marks: dict[str, tuple[float, float]],
    width: float,
    height: float,
) -> list[MarkError]:
    """Error of each placed mark, in ``MARK_NAMES`` order; unplaced marks are skipped."""
    params = camera_params(camera)
    expected = expected_marks(grid)
    results: list[MarkError] = []
    for name in MARK_NAMES:
        if name not in screen_marks:
            continue
        ex = expected[name]
        pt = np.array([screen_marks[name]], dtype=np.float64)
        pt = invert_overlay_distortion(pt, width, height, camera.lens_k1, camera.lens_k2)
        world = unproject_to_plane(params, pt, width, height, ex[2])[0]
        if not np.isfinite(world[:2]).all():
            results.append(MarkError(name, ex, None, None))
            continue
        mx, my = float(world[0]), float(world[1])
        results.append(MarkError(name, ex, (mx, my), math.hypot(mx - ex[0], my - ex[1])))
    return results
