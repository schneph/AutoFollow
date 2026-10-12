# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Moving lights in the web UI: the section, a light's form, hand aiming and the calibration fit."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import pytest

import openfollow.web.discovery as discovery_module
from openfollow.configuration import AppConfig, DmxOutputConfig, MovingLightConfig, load_config, save_config
from openfollow.scene.pan_tilt import FixturePose, Travel, fractions_for
from openfollow.web.routes import _apply_import_data, _strip_broadcast_excluded
from openfollow.web.server import ConfigWebServer
from tests._ports import live_on_free_port

pytestmark = pytest.mark.integration


@pytest.fixture()
def lights_server(tmp_path, monkeypatch):
    for cls in (discovery_module.BeaconSender, discovery_module.BeaconReceiver):
        monkeypatch.setattr(cls, "start", lambda self: None)
        monkeypatch.setattr(cls, "stop", lambda self: None)
    config_path = tmp_path / "config.toml"
    cfg = AppConfig(controlled_marker_ids=[1, 2])
    cfg.dmx_output = DmxOutputConfig(fixtures=[MovingLightConfig(id="spot", name="Spot", marker_id=1)])
    save_config(cfg, str(config_path))
    aims: list = []
    running = {"on": True}

    def aim(fixture_id, fractions):
        aims.append((fixture_id, fractions))
        return running["on"]

    with live_on_free_port(
        lambda port: ConfigWebServer(
            config_path=str(config_path), host="127.0.0.1", port=port, system_name="T", moving_light_aim=aim
        )
    ) as (server, base):
        yield server, base, aims, running


def _request(base: str, path: str, *, form: dict | None = None, body: object = None, method: str = "POST"):
    if form is not None:
        data, ctype = urllib.parse.urlencode(form).encode(), "application/x-www-form-urlencoded"
    elif body is not None:
        data, ctype = json.dumps(body).encode(), "application/json"
    else:
        data, ctype = None, ""
    req = urllib.request.Request(
        f"{base}{path}", data=data, method=method if data is not None or method != "POST" else "POST"
    )
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_the_main_page_carries_the_moving_lights_section(lights_server) -> None:
    _, base, _, _ = lights_server
    status, body = _request(base, "/", method="GET")
    assert status == 200
    assert 'id="dmx-output-section"' in body
    assert "Spot" in body
    assert "Downstage left" in body


def test_saving_the_output_settings(lights_server) -> None:
    server, base, _, _ = lights_server
    status, body = _request(
        base, "/section/dmx_output", form={"enabled": "on", "protocol": "artnet", "host": "10.0.0.4", "fps": "99"}
    )
    assert status == 200
    assert 'id="dmx-output-section"' in body
    dmx = load_config(server.config_path).dmx_output
    assert (dmx.enabled, dmx.protocol, dmx.host, dmx.fps) == (True, "artnet", "10.0.0.4", 44)
    assert [f.id for f in dmx.fixtures] == ["spot"]

    _request(base, "/section/dmx_output", form={"protocol": "dmx512"})
    dmx = load_config(server.config_path).dmx_output
    assert (dmx.enabled, dmx.protocol) == (False, "sacn")


def test_saving_the_grandma2_login(lights_server) -> None:
    server, base, _, _ = lights_server
    status, body = _request(
        base,
        "/section/dmx_output",
        form={
            "protocol": "ma2",
            "host": "10.0.0.4",
            "ma2_port": "30001",
            "ma2_user": " follow ",
            "ma2_password": " pw ",
        },
    )
    assert status == 200
    assert '<option value="ma2" selected>' in body
    dmx = load_config(server.config_path).dmx_output
    assert (dmx.protocol, dmx.ma2_port, dmx.ma2_user, dmx.ma2_password) == ("ma2", 30001, "follow", " pw ")


def test_get_section_renders(lights_server) -> None:
    _, base, _, _ = lights_server
    status, body = _request(base, "/section/dmx_output", method="GET")
    assert status == 200
    assert 'hx-post="/section/moving_light/spot"' in body


def test_adding_saving_and_deleting_a_light(lights_server) -> None:
    server, base, aims, _ = lights_server
    status, body = _request(base, "/section/moving_lights/add", form={})
    assert status == 200
    fixtures = load_config(server.config_path).dmx_output.fixtures
    assert [f.name for f in fixtures] == ["Spot", "Light 2"]
    new = fixtures[1]
    assert new.marker_id == 1
    assert f'data-row-id="{new.id}" open' in body

    status, _ = _request(
        base,
        f"/section/moving_light/{new.id}",
        form={
            "name": "Wash",
            "marker_id": "2",
            "universe": "5",
            "address": "201",
            "pan_channel": "1",
            "tilt_channel": "3",
            "pan_range": "630",
            "tilt_range": "abc",
            "mounting": "floor",
            "pos_x": "2.5",
            "heading": "90",
            "invert_tilt": "on",
            "ma2_fixture": "301",
        },
    )
    assert status == 200
    saved = load_config(server.config_path).dmx_output.fixture(new.id)
    assert saved is not None
    assert (saved.name, saved.marker_id, saved.universe, saved.address) == ("Wash", 2, 5, 201)
    assert (saved.pan_range, saved.tilt_range, saved.mounting, saved.pos_x, saved.heading) == (
        630.0,
        270.0,
        "floor",
        2.5,
        90.0,
    )
    # Unchecked boxes are off: the form posts nothing for them.
    assert (saved.enabled, saved.fine, saved.invert_pan, saved.invert_tilt) == (False, False, False, True)
    assert saved.ma2_fixture == 301

    status, _ = _request(base, f"/section/moving_light/{new.id}/delete", form={})
    assert status == 200
    assert [f.id for f in load_config(server.config_path).dmx_output.fixtures] == ["spot"]
    assert aims[-1] == (new.id, None)


def test_saving_a_light_that_is_gone_is_404(lights_server) -> None:
    _, base, _, _ = lights_server
    status, _ = _request(base, "/section/moving_light/nope", form={"name": "x"})
    assert status == 404


def test_deleting_a_light_that_is_gone_leaves_the_rest(lights_server) -> None:
    server, base, _, _ = lights_server
    status, _ = _request(base, "/section/moving_light/nope/delete", form={})
    assert status == 200
    assert [f.id for f in load_config(server.config_path).dmx_output.fixtures] == ["spot"]


def test_a_light_following_a_marker_this_station_no_longer_controls_says_so(lights_server) -> None:
    server, base, _, _ = lights_server
    cfg = load_config(server.config_path)
    cfg.dmx_output.fixtures[0].marker_id = 9
    save_config(cfg, server.config_path)
    _, body = _request(base, "/section/dmx_output", method="GET")
    assert "Marker 9 (unavailable)" in body


def test_aiming_a_light_by_hand(lights_server) -> None:
    _, base, aims, _ = lights_server
    status, body = _request(base, "/api/moving_light/spot/aim", body={"pan": 0.25, "tilt": 0.75})
    assert status == 200
    assert json.loads(body) == {"aimed": True}
    assert aims[-1] == ("spot", (0.25, 0.75))

    status, body = _request(base, "/api/moving_light/spot/aim", body={"release": True})
    assert (status, json.loads(body)) == (200, {"aimed": False})
    assert aims[-1] == ("spot", None)


@pytest.mark.parametrize(
    "body",
    [
        [1, 2],
        {"pan": "left", "tilt": 0.5},
        {"pan": 0.5},
        {"pan": 1.5, "tilt": 0.5},
        {"pan": 0.5, "tilt": -0.1},
        {"pan": None, "tilt": 0.5},
    ],
)
def test_aiming_refuses_a_bad_body(lights_server, body: object) -> None:
    _, base, aims, _ = lights_server
    status, text = _request(base, "/api/moving_light/spot/aim", body=body)
    assert status == 400
    assert json.loads(text)["error"]
    assert aims == []


def test_aiming_a_light_that_is_gone_is_404(lights_server) -> None:
    _, base, aims, _ = lights_server
    status, text = _request(base, "/api/moving_light/nope/aim", body={"pan": 0.5, "tilt": 0.5})
    assert status == 404
    assert "Reload" in json.loads(text)["error"]
    assert aims == []


def test_aiming_while_the_output_is_off_says_how_to_switch_it_on(lights_server) -> None:
    _, base, _, running = lights_server
    running["on"] = False
    status, text = _request(base, "/api/moving_light/spot/aim", body={"pan": 0.5, "tilt": 0.5})
    assert status == 409
    payload = json.loads(text)
    assert payload["error"] == "The moving lights output is off."
    assert payload["action"]


def test_aiming_without_an_output_attached_is_refused(tmp_path, monkeypatch) -> None:
    for cls in (discovery_module.BeaconSender, discovery_module.BeaconReceiver):
        monkeypatch.setattr(cls, "start", lambda self: None)
        monkeypatch.setattr(cls, "stop", lambda self: None)
    server = ConfigWebServer(config_path=str(tmp_path / "c.toml"), host="127.0.0.1", port=0, system_name="T")
    assert server.aim_moving_light("spot", (0.5, 0.5)) is False


def _marks(truth: FixturePose, travel: Travel) -> list[dict]:
    out = []
    for x, y in ((-4.0, 0.0), (4.0, 0.0), (4.0, 6.0), (-4.0, 6.0), (0.0, 3.0)):
        pan, tilt = fractions_for(truth, travel, (x, y, 0.0))  # type: ignore[misc]
        out.append({"x": x, "y": y, "z": 0.0, "pan": pan, "tilt": tilt})
    return out


def test_solving_a_lights_position_from_marks(lights_server) -> None:
    server, base, _, _ = lights_server
    truth = FixturePose(1.0, -3.0, 7.5, heading=15.0)
    status, text = _request(base, "/api/moving_light/spot/solve", body={"marks": _marks(truth, Travel())})
    assert status == 200
    result = json.loads(text)
    assert (result["pos_x"], result["pos_y"], result["pos_z"]) == pytest.approx((1.0, -3.0, 7.5), abs=0.01)
    assert result["heading"] == pytest.approx(15.0, abs=0.05)
    assert len(result["errors_deg"]) == 5
    assert result["worst_deg"] < 0.05
    # Solving fills the form; it saves nothing.
    assert load_config(server.config_path).dmx_output.fixture("spot").pos_x == 0.0


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"marks": "all"}, 400),
        ([], 400),
        ({"marks": [{"x": 0}]}, 400),
        ({"marks": [{"x": "nan", "y": 0, "z": 0, "pan": 0.5, "tilt": 0.5}] * 4}, 400),
    ],
)
def test_solving_refuses_bad_marks(lights_server, body: object, status: int) -> None:
    _, base, _, _ = lights_server
    got, text = _request(base, "/api/moving_light/spot/solve", body=body)
    assert got == status
    assert json.loads(text)["error"]


def test_solving_with_too_few_marks_asks_for_more(lights_server) -> None:
    _, base, _, _ = lights_server
    marks = _marks(FixturePose(0, 0, 6), Travel())[:3]
    status, text = _request(base, "/api/moving_light/spot/solve", body={"marks": marks})
    assert status == 400
    assert "at least 4 marks" in json.loads(text)["error"]


def test_solving_marks_that_fit_no_position_is_422(lights_server, monkeypatch: pytest.MonkeyPatch) -> None:
    import openfollow.web.routes as routes_module

    monkeypatch.setattr(routes_module, "solve_pose", lambda *_args, **_kw: None)
    _, base, _, _ = lights_server
    marks = _marks(FixturePose(0, 0, 6), Travel())
    status, text = _request(base, "/api/moving_light/spot/solve", body={"marks": marks})
    assert status == 422
    assert "do not fit" in json.loads(text)["error"]


def test_solving_a_light_that_is_gone_is_404(lights_server) -> None:
    _, base, _, _ = lights_server
    status, _ = _request(base, "/api/moving_light/nope/solve", body={"marks": []})
    assert status == 404


@pytest.mark.parametrize(
    ("section", "field", "value", "ok"),
    [
        ("dmx_output", "fps", "30", True),
        ("dmx_output", "fps", "90", False),
        ("dmx_output", "priority", "abc", False),
        ("dmx_output", "host", "10.0.0.1", True),
        ("moving_light", "address", "513", False),
        ("moving_light", "universe", "7", True),
        ("moving_light", "pan_range", "0", False),
        ("moving_light", "base_pitch", "10", True),
        ("moving_light", "heading", "abc", False),
        ("dmx_output", "ma2_port", "70000", False),
        ("dmx_output", "ma2_user", "follow", True),
        ("dmx_output", "protocol", "ma2", True),
        ("moving_light", "ma2_fixture", "101", True),
        ("moving_light", "ma2_fixture", "-1", False),
    ],
)
def test_fields_validate_on_blur(lights_server, section: str, field: str, value: str, ok: bool) -> None:
    _, base, _, _ = lights_server
    status, body = _request(
        base, f"/api/validate/{section}/{field}?{urllib.parse.urlencode({field: value})}", method="GET"
    )
    assert status == 200
    assert (body.strip() == "") is ok


def test_moving_lights_are_never_broadcast_to_peers() -> None:
    assert "dmx_output" not in _strip_broadcast_excluded({"dmx_output": {}, "grid": {}})


def test_an_import_rebuilds_the_moving_lights() -> None:
    cfg = AppConfig()
    cfg.dmx_output = DmxOutputConfig(fixtures=[MovingLightConfig(id="old")])
    data = {"dmx_output": {"enabled": True, "protocol": "artnet", "fixtures": [{"id": "new", "universe": 0}]}}
    cfg = _apply_import_data(cfg, data)
    assert cfg.dmx_output.protocol == "artnet"
    assert [f.id for f in cfg.dmx_output.fixtures] == ["new"]
    assert cfg.dmx_output.fixtures[0].universe == 0
