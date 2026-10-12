# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Stage floor to projected image: the projection area and its ``[u]`` / ``[v]`` sources."""

from __future__ import annotations

from typing import Any

import pytest

from openfollow.configuration import GridConfig, OscTransmitterConfig, OscTransmittersConfig
from openfollow.osc.template import RenderContext, RenderError, compile_template, osc_arg_for, render
from openfollow.osc.transmitter import OscTransmitterManager
from openfollow.scene.projection import floor_projection, projection_corners

pytestmark = pytest.mark.unit

_GRID_AREA = [(-5.0, 6.0), (5.0, 6.0), (5.0, 0.0), (-5.0, 0.0)]


def _uv(corners: list[tuple[float, float]], x: float, y: float) -> tuple[float, float] | None:
    projection = floor_projection(corners)
    assert projection is not None
    return projection.uv(x, y)


# ---------------------------------------------------------------------------
# Corners
# ---------------------------------------------------------------------------


def test_corners_follow_the_grid_as_the_audience_sees_it() -> None:
    grid = GridConfig(width=10.0, depth=6.0, x_offset=1.0, y_offset=4.0)
    # Top = upstage (+Y), left = audience left (-X).
    assert projection_corners(grid) == [(-4.0, 7.0), (6.0, 7.0), (6.0, 1.0), (-4.0, 1.0)]


def test_corners_come_from_the_config_when_the_grid_is_not_used() -> None:
    grid = GridConfig(
        projection_use_grid=False,
        projection_tl_x=-3.0,
        projection_tl_y=8.0,
        projection_tr_x=4.0,
        projection_tr_y=7.5,
        projection_br_x=3.5,
        projection_br_y=1.0,
        projection_bl_x=-2.5,
        projection_bl_y=0.5,
    )
    assert projection_corners(grid) == [(-3.0, 8.0), (4.0, 7.5), (3.5, 1.0), (-2.5, 0.5)]


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        ((-5.0, 6.0), (0.0, 0.0)),
        ((5.0, 6.0), (1.0, 0.0)),
        ((5.0, 0.0), (1.0, 1.0)),
        ((-5.0, 0.0), (0.0, 1.0)),
        ((0.0, 3.0), (0.5, 0.5)),
        ((2.5, 4.5), (0.75, 0.25)),
    ],
)
def test_rectangle_maps_linearly(point: tuple[float, float], expected: tuple[float, float]) -> None:
    assert _uv(_GRID_AREA, *point) == pytest.approx(expected)


def test_keystoned_area_maps_its_corners_to_the_image_corners() -> None:
    # A projector hung downstage throws a wider image upstage.
    corners = [(-7.0, 8.0), (7.0, 8.0), (3.0, 0.0), (-3.0, 0.0)]
    for corner, expected in zip(corners, [(0, 0), (1, 0), (1, 1), (0, 1)], strict=True):
        assert _uv(corners, *corner) == pytest.approx(expected, abs=1e-9)
    # Halfway across stays the image's middle column at any depth.
    assert _uv(corners, 0.0, 4.0)[0] == pytest.approx(0.5)  # type: ignore[index]


def test_corner_order_reversed_maps_the_same_way() -> None:
    """A clockwise and a counter-clockwise listing are both convex; neither flips the sign of w."""
    mirrored = [(5.0, 6.0), (-5.0, 6.0), (-5.0, 0.0), (5.0, 0.0)]
    assert _uv(mirrored, 2.5, 4.5) == pytest.approx((0.25, 0.25))


def test_points_outside_the_area_clamp_to_the_image_edge() -> None:
    assert _uv(_GRID_AREA, -20.0, 3.0) == pytest.approx((0.0, 0.5))
    assert _uv(_GRID_AREA, 0.0, 30.0) == pytest.approx((0.5, 0.0))


def test_point_beyond_the_horizon_has_no_image_position() -> None:
    # A strongly keystoned area: its horizon (w = 0) lies a short way past the narrow edge.
    corners = [(-1.0, 1.0), (1.0, 1.0), (10.0, 0.0), (-10.0, 0.0)]
    assert _uv(corners, 0.0, 0.5) is not None
    assert _uv(corners, 0.0, 50.0) is None


@pytest.mark.parametrize(
    "corners",
    [
        pytest.param([(-5.0, 6.0), (5.0, 0.0), (5.0, 6.0), (-5.0, 0.0)], id="bow-tie"),
        pytest.param([(-5.0, 6.0), (0.0, 1.0), (5.0, 6.0), (0.0, 0.0)], id="concave"),
        pytest.param([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)], id="collinear"),
        pytest.param([(0.0, 0.0)] * 4, id="one-point"),
        pytest.param([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], id="three-corners"),
        pytest.param([(float("nan"), 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], id="nan"),
    ],
)
def test_unusable_area_has_no_mapping(corners: list[tuple[float, float]]) -> None:
    assert floor_projection(corners) is None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_projection_defaults_follow_the_grid() -> None:
    grid = GridConfig()
    assert grid.projection_use_grid is True
    assert projection_corners(GridConfig(projection_use_grid=False)) == _GRID_AREA


@pytest.mark.parametrize("bad", ["wide", None, float("inf"), float("nan"), [1.0]])
def test_projection_corner_falls_back_to_its_default(bad: Any) -> None:
    grid = GridConfig(projection_tl_x=bad, projection_br_y=bad)
    assert grid.projection_tl_x == -5.0
    assert grid.projection_br_y == 0.0


def test_projection_corner_coerces_numeric_strings() -> None:
    assert GridConfig(projection_tr_x="7.5").projection_tr_x == 7.5


@pytest.mark.parametrize(("raw", "expected"), [("false", False), ("true", True), (False, False), ("nonsense", True)])
def test_projection_use_grid_coerces_to_bool(raw: Any, expected: bool) -> None:
    assert GridConfig(projection_use_grid=raw).projection_use_grid is expected


# ---------------------------------------------------------------------------
# [u] / [v] placeholders
# ---------------------------------------------------------------------------


def _ctx(
    pos: tuple[float, float, float] = (2.5, 4.5, 1.0),
    *,
    marker_id: int | None = 0,
    projection: Any = "grid",
    marker_resolver: Any = None,
) -> RenderContext:
    if projection == "grid":
        mapping = floor_projection(_GRID_AREA)
        assert mapping is not None
        projection = mapping.uv
    return RenderContext(
        pos_m=pos,
        grid_w=10.0,
        grid_d=6.0,
        grid_h=0.0,
        z_offset=0.0,
        marker_id=marker_id,
        marker_resolver=marker_resolver,
        projection=projection,
    )


def test_u_and_v_render_the_image_position() -> None:
    assert render(compile_template("[u] [v]"), _ctx()) == "0.75 0.25"
    assert osc_arg_for(compile_template("[u]"), _ctx()) == ("f", pytest.approx(0.75))


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("[u.inv]", ("f", 0.25)),
        ("[v.pct]", ("f", 25.0)),
        ("[u.int:0-1920]", ("i", 1440)),
        ("[v.scale:-1-1]", ("f", -0.5)),
    ],
)
def test_u_and_v_take_the_fader_transforms(template: str, expected: tuple[str, float]) -> None:
    tag, value = osc_arg_for(compile_template(template), _ctx())
    assert tag == expected[0]
    assert value == pytest.approx(expected[1])


@pytest.mark.parametrize("template", ["[u.frac]", "[v.frac]"])
def test_position_transforms_are_not_projection_transforms(template: str) -> None:
    ct = compile_template(template)
    assert len(ct) == 1 and type(ct[0]).__name__ == "_Literal"


def test_explicit_marker_reference_reads_that_marker() -> None:
    ctx = _ctx(pos=(99.0, 99.0, 0.0), marker_resolver={3: (-5.0, 0.0, 0.0)}.get)
    assert render(compile_template("[u:3] [v:3]"), ctx) == "0 1"


def test_bare_u_without_a_default_marker_is_a_render_error() -> None:
    with pytest.raises(RenderError, match="no default marker"):
        render(compile_template("[u]"), _ctx(marker_id=None))


def test_unusable_area_is_a_render_error_naming_the_area() -> None:
    with pytest.raises(RenderError) as exc:
        render(compile_template("[v]"), _ctx(projection=None))
    assert exc.value.hint == "projection area is not a convex quadrilateral"


def test_point_beyond_the_horizon_is_a_render_error() -> None:
    with pytest.raises(RenderError) as exc:
        render(compile_template("[u]"), _ctx(projection=lambda _x, _y: None))
    assert exc.value.hint == "marker is beyond the projection's horizon"


# ---------------------------------------------------------------------------
# Transmitter wiring
# ---------------------------------------------------------------------------


def test_transmitter_sends_u_v_from_the_live_projection() -> None:
    from tests.test_osc_transmitter import _destinations, _FakeMarker, _FakeOscService, _row

    mapping = floor_projection(_GRID_AREA)
    assert mapping is not None
    current: list[Any] = [None]
    service = _FakeOscService()
    manager = OscTransmitterManager(
        osc_service=service,  # type: ignore[arg-type]
        marker_provider={0: _FakeMarker((2.5, 4.5, 0.0))}.get,
        grid_provider=lambda: (10.0, 6.0, 0.0, 0.0),
        projection_provider=lambda: current[0],
    )
    manager.restart(OscTransmittersConfig(transmitters=[_row(args=["[u]", "[v]"])]), _destinations())
    # No usable area: the row skips.
    manager._tick_once()
    assert service.calls == []
    current[0] = mapping.uv
    manager._tick_once()
    assert service.calls[0][1] == [pytest.approx(0.75), pytest.approx(0.25)]


def test_transmitter_without_a_projection_provider_skips_u_rows() -> None:
    from tests.test_osc_transmitter import _destinations, _FakeMarker, _FakeOscService, _row

    service = _FakeOscService()
    manager = OscTransmitterManager(
        osc_service=service,  # type: ignore[arg-type]
        marker_provider={0: _FakeMarker((2.5, 4.5, 0.0))}.get,
        grid_provider=lambda: (10.0, 6.0, 0.0, 0.0),
    )
    manager.restart(OscTransmittersConfig(transmitters=[_row(args=["[u]"])]), _destinations())
    manager._tick_once()
    assert service.calls == []


def test_row_config_accepts_u_v() -> None:
    assert OscTransmitterConfig(args=["[u]", "[v.int:0-1080]"]).args == ["[u]", "[v.int:0-1080]"]
