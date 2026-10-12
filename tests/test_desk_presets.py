# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Tests for the desk cue presets a trigger zone can be filled from."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import pytest

import openfollow.web.discovery as discovery_module
from openfollow.osc.desk_presets import PresetError, magicq_zone_cues
from openfollow.web.server import ConfigWebServer
from tests._ports import live_on_free_port


@pytest.mark.unit
@pytest.mark.parametrize(
    ("playback", "cue", "first"),
    [
        (1, "", "/pb/1/go"),
        ("12", "", "/pb/12/go"),
        (" 999 ", "  ", "/pb/999/go"),
        ("3.0", "", "/pb/3/go"),
        (4, "7", "/pb/4/7"),
        (4, " 2.5 ", "/pb/4/2.5"),
    ],
)
def test_magicq_zone_cues_go_on_entry_and_release_on_exit(playback: object, cue: object, first: str) -> None:
    cues = magicq_zone_cues(playback, cue)
    pb = first.split("/")[2]
    assert cues == {"osc_address_first_entry": first, "osc_address_final_exit": f"/pb/{pb}/release"}


@pytest.mark.unit
@pytest.mark.parametrize("playback", ["", "0", "-1", "1000", "2.5", "one", None, "nan", "inf", True])
def test_magicq_zone_cues_refuse_a_bad_playback(playback: object) -> None:
    with pytest.raises(PresetError, match="Playback must be a whole number from 1 to 999."):
        magicq_zone_cues(playback)


@pytest.mark.unit
@pytest.mark.parametrize("cue", ["0", "-2", "abc", "2.", ".5", "1.2.3", "/pb/1", "12345"])
def test_magicq_zone_cues_refuse_a_bad_cue(cue: str) -> None:
    with pytest.raises(PresetError, match="Cue must be a number above 0"):
        magicq_zone_cues(1, cue)


@pytest.fixture()
def live_server(tmp_path, monkeypatch):  # noqa: ANN001, ANN201
    for cls in (discovery_module.BeaconSender, discovery_module.BeaconReceiver):
        monkeypatch.setattr(cls, "start", lambda self: None)
        monkeypatch.setattr(cls, "stop", lambda self: None)
    with live_on_free_port(
        lambda port: ConfigWebServer(
            config_path=str(tmp_path / "config.toml"), host="127.0.0.1", port=port, system_name="Desk"
        )
    ) as (server, base):
        yield server, base


def _get(base: str, path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


@pytest.mark.integration
def test_magicq_preset_route_answers_the_addresses(live_server) -> None:  # noqa: ANN001
    _, base = live_server
    status, body = _get(base, "/api/zones/preset/magicq?" + urllib.parse.urlencode({"playback": "5", "cue": "2.5"}))
    assert status == 200
    assert json.loads(body) == {"osc_address_first_entry": "/pb/5/2.5", "osc_address_final_exit": "/pb/5/release"}


@pytest.mark.integration
@pytest.mark.parametrize("query", ["", "?playback=0", "?playback=2&cue=x"])
def test_magicq_preset_route_refuses_what_magicq_would(live_server, query: str) -> None:  # noqa: ANN001
    _, base = live_server
    status, body = _get(base, "/api/zones/preset/magicq" + query)
    assert status == 400
    assert json.loads(body)["error"].endswith(".")


@pytest.mark.integration
def test_zone_editor_offers_the_magicq_fill(live_server) -> None:  # noqa: ANN001
    _, base = live_server
    _, body = _get(base, "/")
    assert 'id="zone-magicq-fill"' in body
    assert "/api/zones/preset/magicq?playback=" in body


@pytest.mark.integration
def test_psn_help_covers_magicq(live_server) -> None:  # noqa: ANN001
    _, base = live_server
    status, body = _get(base, "/help/psn.html")
    assert status == 200
    assert "ChamSys MagicQ" in body
