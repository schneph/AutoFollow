# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Stage floor to projected image: where a marker lands in a projector's 0-1 frame.

A media server places content by a normalised position in its output (0-1
across, 0-1 down). The projection area is the quadrilateral the projected
image covers on the stage floor, its corners in PSN-absolute metres; a
homography maps the floor onto the unit square, so a keystoned or rotated
projection still lands the content under the performer.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt

from openfollow.scene.solver import compute_homography

# Image corners, in the order the projection area lists its floor corners.
_UNIT_SQUARE = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float64)


def projection_corners(grid: Any) -> list[tuple[float, float]]:
    """Floor corners of the image's top-left, top-right, bottom-right, bottom-left.

    With ``projection_use_grid`` the image covers the grid as the audience
    sees it: top = upstage, left = audience left (stage right, -X).
    """
    if grid.projection_use_grid:
        hw, hd = grid.width / 2.0, grid.depth / 2.0
        ox, oy = grid.x_offset, grid.y_offset
        return [(ox - hw, oy + hd), (ox + hw, oy + hd), (ox + hw, oy - hd), (ox - hw, oy - hd)]
    return [
        (grid.projection_tl_x, grid.projection_tl_y),
        (grid.projection_tr_x, grid.projection_tr_y),
        (grid.projection_br_x, grid.projection_br_y),
        (grid.projection_bl_x, grid.projection_bl_y),
    ]


def _is_convex(corners: npt.NDArray[np.float64]) -> bool:
    crosses = []
    for i in range(4):
        a, b, c = corners[i], corners[(i + 1) % 4], corners[(i + 2) % 4]
        crosses.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
    return all(x > 1e-9 for x in crosses) or all(x < -1e-9 for x in crosses)


class FloorProjection:
    """Maps a floor point to its ``(u, v)`` in the projected image, clamped to 0-1."""

    def __init__(self, matrix: npt.NDArray[np.float64]) -> None:
        self._h = matrix

    def uv(self, x: float, y: float) -> tuple[float, float] | None:
        """``None`` for a point beyond the projection's horizon, where no image lands."""
        p = self._h @ np.array([x, y, 1.0])
        if p[2] <= 1e-12:
            return None
        u, v = float(p[0] / p[2]), float(p[1] / p[2])
        return min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0)


def floor_projection(corners: list[tuple[float, float]]) -> FloorProjection | None:
    """The mapping for four floor corners, or ``None`` when they are not a convex quadrilateral."""
    pts = np.array(corners, dtype=np.float64)
    if pts.shape != (4, 2) or not np.isfinite(pts).all() or not _is_convex(pts):
        return None
    matrix = compute_homography(pts, _UNIT_SQUARE)
    # A homography is defined up to scale, sign included: make w positive inside the area.
    centre = matrix @ np.array([*pts.mean(axis=0), 1.0])
    return FloorProjection(matrix if centre[2] > 0 else -matrix)
