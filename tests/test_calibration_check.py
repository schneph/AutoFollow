# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Tests for the calibration check: floor-mark error against a saved calibration."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import numpy as np
import pytest

import openfollow.web.discovery as discovery_module
from openfollow.configuration import AppConfig, CameraConfig, GridConfig, save_config
from openfollow.scene.calibration_check import (
    CAUTION_M,
    MARK_NAMES,
    OK_M,
    MarkError,
    error_level,
    expected_marks,
    measure_marks,
    project_marks,
)
from openfollow.scene.solver import apply_overlay_distortion, project_points
from openfollow.units import UnitSystem, format_small_length
from openfollow.web.server import ConfigWebServer
from tests._ports import live_on_free_port

W, H = 1920.0, 1080.0


def _camera(**kw: float) -> CameraConfig:
    base = {"pos_x": 0.0, "pos_y": -10.0, "pos_z": 8.0, "pitch": -30.0, "yaw": 0.0, "roll": 0.0, "fov": 60.0}
    base.update(kw)
    return CameraConfig(**base)  # type: ignore[arg-type]


def _grid(**kw: float) -> GridConfig:
    base = {"width": 10.0, "depth": 6.0, "x_offset": 0.0, "y_offset": 3.0, "z_offset": 0.0}
    base.update(kw)
    return GridConfig(**base)  # type: ignore[arg-type]


def _screen_of(camera: CameraConfig, world: tuple[float, float, float]) -> tuple[float, float]:
    params = np.array([camera.pos_x, camera.pos_y, camera.pos_z, camera.pitch, camera.yaw, camera.roll, camera.fov])
    pt = apply_overlay_distortion(
        project_points(params, np.array([world], dtype=np.float64), W, H), W, H, camera.lens_k1, camera.lens_k2
    )[0]
    return float(pt[0]), float(pt[1])


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_expected_marks_put_stage_left_at_positive_x() -> None:
    marks = expected_marks(_grid(width=8.0, depth=4.0, x_offset=1.0, y_offset=2.0, z_offset=0.5))
    assert marks == {
        "DSL": (5.0, 0.0, 0.5),
        "DSR": (-3.0, 0.0, 0.5),
        "USR": (-3.0, 4.0, 0.5),
        "USL": (5.0, 4.0, 0.5),
        "REF": (0.0, 0.0, 0.0),
    }


@pytest.mark.unit
@pytest.mark.parametrize("lens", [(0.0, 0.0), (0.2, 0.05)])
@pytest.mark.parametrize("z_offset", [0.0, 0.6])
def test_marks_placed_where_drawn_measure_zero(lens: tuple[float, float], z_offset: float) -> None:
    camera = _camera(lens_k1=lens[0], lens_k2=lens[1])
    grid = _grid(z_offset=z_offset)
    drawn = project_marks(camera, grid, W, H)
    placed = {n: p for n, p in drawn.items() if p is not None}
    results = measure_marks(camera, grid, placed, W, H)
    assert [r.name for r in results] == list(MARK_NAMES)
    for r in results:
        assert r.error_m == pytest.approx(0.0, abs=1e-6)
        assert r.level == "ok"


@pytest.mark.unit
@pytest.mark.parametrize("dx,dy", [(0.2, 0.0), (0.0, -0.45), (0.3, 0.4)])
def test_a_mark_off_its_tape_reports_the_stage_distance(dx: float, dy: float) -> None:
    camera, grid = _camera(), _grid()
    ex = expected_marks(grid)["USL"]
    placed = {"USL": _screen_of(camera, (ex[0] + dx, ex[1] + dy, ex[2]))}
    (result,) = measure_marks(camera, grid, placed, W, H)
    assert result.name == "USL"
    assert result.error_m == pytest.approx(np.hypot(dx, dy), abs=1e-6)
    assert result.measured == pytest.approx((ex[0] + dx, ex[1] + dy), abs=1e-6)


@pytest.mark.unit
def test_unplaced_marks_are_left_out() -> None:
    camera, grid = _camera(), _grid()
    drawn = project_marks(camera, grid, W, H)
    results = measure_marks(camera, grid, {"REF": drawn["REF"], "DSR": drawn["DSR"]}, W, H)  # type: ignore[dict-item]
    assert [r.name for r in results] == ["DSR", "REF"]


@pytest.mark.unit
def test_a_mark_placed_above_the_horizon_cannot_be_measured() -> None:
    camera, grid = _camera(pitch=-5.0), _grid()
    (result,) = measure_marks(camera, grid, {"DSL": (W / 2, 0.0)}, W, H)
    assert result.measured is None
    assert result.error_m is None
    assert result.level == "error"


@pytest.mark.unit
def test_a_mark_behind_the_camera_is_not_drawn() -> None:
    marks = project_marks(_camera(), _grid(y_offset=-20.0), W, H)
    assert marks["DSL"] is None
    assert marks["REF"] is not None


@pytest.mark.unit
@pytest.mark.parametrize(
    "error_m,level",
    [
        (0.0, "ok"),
        (OK_M, "ok"),
        (OK_M + 1e-6, "caution"),
        (CAUTION_M, "caution"),
        (CAUTION_M + 1e-6, "error"),
        (5.0, "error"),
        (None, "error"),
    ],
)
def test_error_level_bounds(error_m: float | None, level: str) -> None:
    assert error_level(error_m) == level
    assert MarkError("DSL", (0.0, 0.0, 0.0), None, error_m).level == level


@pytest.mark.unit
@pytest.mark.parametrize(
    "meters,units,text",
    [
        (0.0, UnitSystem.METRIC, "0 cm"),
        (0.124, UnitSystem.METRIC, "12 cm"),
        (1.5, UnitSystem.METRIC, "150 cm"),
        (0.0254, UnitSystem.IMPERIAL, "1.0 in"),
        (0.12, UnitSystem.IMPERIAL, "4.7 in"),
    ],
)
def test_format_small_length(meters: float, units: UnitSystem, text: str) -> None:
    assert format_small_length(meters, units) == text


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@pytest.fixture()
def live_server(tmp_path, monkeypatch):  # noqa: ANN001, ANN201
    for cls in (discovery_module.BeaconSender, discovery_module.BeaconReceiver):
        monkeypatch.setattr(cls, "start", lambda self: None)
        monkeypatch.setattr(cls, "stop", lambda self: None)
    config_path = tmp_path / "config.toml"
    cfg = AppConfig()
    cfg.camera = _camera()
    cfg.grid = _grid()
    save_config(cfg, str(config_path))
    with live_on_free_port(
        lambda port: ConfigWebServer(config_path=str(config_path), host="127.0.0.1", port=port, system_name="Cal")
    ) as (server, base):
        yield server, base


def _get(base: str, path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _post(base: str, path: str, body: bytes) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{base}{path}", data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def _check(base: str, marks: object, **extra: object) -> tuple[int, dict]:
    payload = {"image_width": W, "image_height": H, "marks": marks, **extra}
    return _post(base, "/api/calibration/check", json.dumps(payload).encode())


@pytest.mark.integration
def test_page_renders_and_is_linked_from_settings(live_server) -> None:  # noqa: ANN001
    _, base = live_server
    status, body = _get(base, "/calibration-check")
    assert status == 200
    assert "Calibration Check" in body
    assert 'data-help="calibration_check"' in body
    _, index = _get(base, "/")
    assert 'href="/calibration-check"' in index


@pytest.mark.integration
def test_help_doc_is_served(live_server) -> None:  # noqa: ANN001
    _, base = live_server
    status, body = _get(base, "/help/calibration_check.html")
    assert status == 200
    assert "Off the stage plane" in body


@pytest.mark.integration
def test_marks_route_projects_the_saved_calibration(live_server) -> None:  # noqa: ANN001
    _, base = live_server
    status, body = _get(base, f"/api/calibration/marks?image_width={W}&image_height={H}")
    assert status == 200
    expected = project_marks(_camera(), _grid(), W, H)
    marks = json.loads(body)["marks"]
    assert set(marks) == set(MARK_NAMES)
    for name, pt in expected.items():
        assert marks[name] == pytest.approx(list(pt))  # type: ignore[arg-type]


@pytest.mark.integration
def test_marks_route_sends_null_for_a_mark_behind_the_camera(live_server) -> None:  # noqa: ANN001
    server, base = live_server
    cfg = AppConfig()
    cfg.camera = _camera()
    cfg.grid = _grid(y_offset=-20.0)
    save_config(cfg, server.config_path)
    _, body = _get(base, f"/api/calibration/marks?image_width={W}&image_height={H}")
    assert json.loads(body)["marks"]["DSL"] is None


@pytest.mark.integration
@pytest.mark.parametrize("query", ["", "?image_width=0&image_height=1080", "?image_width=wide&image_height=1"])
def test_marks_route_rejects_a_bad_canvas(live_server, query: str) -> None:  # noqa: ANN001
    _, base = live_server
    status, body = _get(base, "/api/calibration/marks" + query)
    assert status == 400
    assert "error" in json.loads(body)


@pytest.mark.integration
def test_check_route_reports_each_mark_and_the_worst(live_server) -> None:  # noqa: ANN001
    _, base = live_server
    camera, grid = _camera(), _grid()
    drawn = project_marks(camera, grid, W, H)
    ex = expected_marks(grid)["DSR"]
    status, body = _check(
        base, {"REF": list(drawn["REF"]), "DSR": list(_screen_of(camera, (ex[0] + 0.2, ex[1], ex[2])))}
    )
    assert status == 200
    by_name = {m["name"]: m for m in body["marks"]}
    assert by_name["REF"]["level"] == "ok"
    assert by_name["REF"]["error_text"] == "0 cm"
    assert by_name["DSR"]["level"] == "caution"
    assert by_name["DSR"]["error_text"] == "20 cm"
    assert body["worst_m"] == pytest.approx(0.2, abs=1e-6)
    assert body["worst_text"] == "20 cm"
    assert body["level"] == "caution"


@pytest.mark.integration
def test_check_route_speaks_imperial(live_server) -> None:  # noqa: ANN001
    server, base = live_server
    cfg = AppConfig()
    cfg.camera, cfg.grid = _camera(), _grid()
    cfg.ui.unit_system = "imperial"
    save_config(cfg, server.config_path)
    ex = expected_marks(cfg.grid)["USR"]
    _, body = _check(base, {"USR": list(_screen_of(cfg.camera, (ex[0], ex[1] + 0.0254, ex[2])))})
    assert body["marks"][0]["error_text"] == "1.0 in"


@pytest.mark.integration
def test_check_route_flags_a_mark_off_the_stage_plane(live_server) -> None:  # noqa: ANN001
    server, base = live_server
    cfg = AppConfig()
    cfg.camera, cfg.grid = _camera(pitch=-5.0), _grid()
    save_config(cfg, server.config_path)
    drawn = project_marks(cfg.camera, cfg.grid, W, H)
    _, body = _check(base, {"REF": list(drawn["REF"]), "USL": [W / 2, 0.0]})
    usl = next(m for m in body["marks"] if m["name"] == "USL")
    assert usl["error_m"] is None
    assert usl["error_text"] == "Off the stage plane"
    assert body["worst_m"] is None
    assert body["worst_text"] == "Off the stage plane"
    assert body["level"] == "error"


@pytest.mark.integration
def test_check_route_with_nothing_placed(live_server) -> None:  # noqa: ANN001
    _, base = live_server
    status, body = _check(base, {})
    assert status == 200
    assert body == {"marks": [], "worst_m": None, "worst_text": "", "level": "ok"}


@pytest.mark.integration
@pytest.mark.parametrize(
    "payload",
    [
        [1, 2],
        {"image_width": W, "image_height": H},
        {"image_width": W, "image_height": H, "marks": [1, 2]},
        {"image_width": W, "image_height": H, "marks": {"XYZ": [1, 2]}},
        {"image_width": W, "image_height": H, "marks": {"DSL": [1, 2, 3]}},
        {"image_width": W, "image_height": H, "marks": {"DSL": "here"}},
        {"image_width": W, "image_height": H, "marks": {"DSL": ["a", "b"]}},
        {"image_width": W, "image_height": H, "marks": {"DSL": [float("nan"), 1]}},
        {"image_width": 0, "image_height": H, "marks": {}},
        {"image_width": "wide", "image_height": H, "marks": {}},
    ],
)
def test_check_route_rejects_malformed_bodies(live_server, payload: object) -> None:  # noqa: ANN001
    _, base = live_server
    status, body = _post(base, "/api/calibration/check", json.dumps(payload).encode())
    assert status == 400
    assert "error" in body


@pytest.mark.integration
@pytest.mark.parametrize("raw", [b"not json", b"null", b"\xff"])
def test_check_route_rejects_invalid_json(live_server, raw: bytes) -> None:  # noqa: ANN001
    _, base = live_server
    status, body = _post(base, "/api/calibration/check", raw)
    assert status == 400
    assert body == {"error": "Invalid JSON"}
