# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Freeze: every controlled marker held, from the key, the web UI or a desk."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from openfollow.configuration import AppConfig, ControllerConfig
from openfollow.input.gamepad import GamepadUpdate
from openfollow.osc.show_control import FreezeCommand
from openfollow.psn.marker import Marker
from openfollow.runtime import app_modes
from openfollow.runtime.output_freeze import (
    STATUS_FLAG,
    check_output_freeze,
    outputs_frozen,
    set_outputs_frozen,
    sync_output_freeze,
)
from openfollow.services import WebCommandQueue
from openfollow.web.routes import apply_section_data

pytestmark = pytest.mark.unit


class _Server:
    def __init__(self, *ids: int) -> None:
        self.by_id = {mid: Marker(mid, f"T{mid}") for mid in ids}

    def get_marker(self, marker_id: int) -> Marker | None:
        return self.by_id.get(marker_id)


class _Input:
    def __init__(self, *commands: FreezeCommand) -> None:
        self.commands = list(commands)

    def flush_freeze_commands(self) -> list[FreezeCommand]:
        commands, self.commands = self.commands, []
        return commands


def _app(controlled: tuple[int, ...] = (1, 2), *, registered: tuple[int, ...] = (1, 2, 5)) -> SimpleNamespace:
    app = SimpleNamespace(
        _controlled_ids=list(controlled),
        _server=_Server(*registered),
        _runtime_services=SimpleNamespace(_status_flags={}),
        _web_commands=WebCommandQueue(),
        _input_manager=_Input(),
    )
    for mid, marker in app._server.by_id.items():
        marker.set_pos(float(mid), 0.0, 0.0)
    return app


def _held(app: SimpleNamespace) -> dict[int, bool]:
    return {mid: marker.held for mid, marker in app._server.by_id.items()}


def test_freezing_holds_every_controlled_marker_and_says_so() -> None:
    app = _app()
    assert set_outputs_frozen(app, True)

    assert outputs_frozen(app)
    assert _held(app) == {1: True, 2: True, 5: False}
    app._server.by_id[1].set_pos(9.0, 9.0, 9.0)
    assert app._server.by_id[1].pos == (1.0, 0.0, 0.0)
    assert app._runtime_services._status_flags[STATUS_FLAG] == ("caution", "Outputs frozen: markers held")
    assert app._web_commands.outputs_frozen()


def test_releasing_lets_every_marker_move_and_clears_the_row() -> None:
    app = _app()
    set_outputs_frozen(app, True)
    assert set_outputs_frozen(app, False)

    assert not outputs_frozen(app)
    assert _held(app) == {1: False, 2: False, 5: False}
    app._server.by_id[1].set_pos(9.0, 9.0, 9.0)
    assert app._server.by_id[1].pos == (9.0, 9.0, 9.0)
    assert app._runtime_services._status_flags[STATUS_FLAG] is None
    assert not app._web_commands.outputs_frozen()


def test_toggle_flips_the_state() -> None:
    app = _app()
    assert set_outputs_frozen(app, None)
    assert outputs_frozen(app)
    assert set_outputs_frozen(app, None)
    assert not outputs_frozen(app)


@pytest.mark.parametrize("frozen", [True, False])
def test_asking_for_the_current_state_changes_nothing(frozen: bool) -> None:
    app = _app()
    app._outputs_frozen = frozen
    assert not set_outputs_frozen(app, frozen)


def test_an_app_that_never_froze_reads_as_released() -> None:
    assert not outputs_frozen(SimpleNamespace())


def test_a_marker_taken_under_control_while_frozen_is_held_on_the_next_poll() -> None:
    app = _app()
    set_outputs_frozen(app, True)
    app._controlled_ids.append(5)
    sync_output_freeze(app)
    assert _held(app)[5]


def test_sync_skips_a_controlled_marker_that_is_not_registered_and_a_missing_server() -> None:
    app = _app(controlled=(1, 7))
    app._outputs_frozen = True
    sync_output_freeze(app)
    assert _held(app)[1]
    app._server = None
    sync_output_freeze(app)
    assert app._web_commands.outputs_frozen()


def test_check_applies_web_then_desk_requests_in_order() -> None:
    app = _app()
    app._web_commands.request_freeze(True)
    app._input_manager = _Input(FreezeCommand(frozen=False), FreezeCommand())

    check_output_freeze(app)

    assert outputs_frozen(app)
    assert app._web_commands.consume_freeze_requests() == []


def test_check_without_input_still_takes_web_requests_and_syncs() -> None:
    app = _app()
    app._input_manager = None
    app._web_commands.request_freeze(None)
    check_output_freeze(app)
    assert outputs_frozen(app)
    assert _held(app)[2]


# --------------------------------------------------------------------------- #
# Operator Screen: the freeze key and the gamepad button
# --------------------------------------------------------------------------- #


def _screen_app(**kwargs: object) -> SimpleNamespace:
    app = _app()
    app.__dict__.update(
        _button_detection=None,
        _settings_menu_active=False,
        _video_receiver=None,
        _url_editor_active=False,
        _browser_active=False,
        _source_type_selection_active=False,
        _field_choice_active=False,
        _config=AppConfig(),
        _selected_id=None,
        _settings_key_pressed=False,
        _show_hud_help=False,
    )
    app.__dict__.update(kwargs)
    return app


def test_the_freeze_key_toggles_the_freeze() -> None:
    app = _screen_app()
    app_modes.handle_key_press(app, "f")
    assert outputs_frozen(app)
    app_modes.handle_key_press(app, "f")
    assert not outputs_frozen(app)


def test_an_unbound_freeze_key_does_nothing() -> None:
    app = _screen_app()
    app._config.controller.key_freeze = ""
    app_modes.handle_key_press(app, "f")
    assert not outputs_frozen(app)


def test_the_gamepad_freeze_button_toggles_the_freeze() -> None:
    class _InputManager:
        keyboard_handler = SimpleNamespace(keys=set())

        def update(self, dt):  # noqa: ANN001, ANN201
            return GamepadUpdate(freeze_pressed=True)

    app = _screen_app(_input_manager=_InputManager())
    app_modes.process_input(app, 0.01)
    assert outputs_frozen(app)


# --------------------------------------------------------------------------- #
# Bindings in config
# --------------------------------------------------------------------------- #


def test_freeze_defaults_to_f_on_the_keyboard_and_unbound_on_a_gamepad() -> None:
    cc = ControllerConfig()
    assert cc.key_freeze == "f"
    assert cc.btn_freeze == ""


@pytest.mark.parametrize("value", ["NOPE", None, 3, True])
def test_an_invalid_freeze_button_falls_back_to_unbound(value: object) -> None:
    assert ControllerConfig(btn_freeze=value).btn_freeze == ""  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["w", None, 3, "two"])
def test_an_invalid_freeze_key_falls_back_to_f(value: object) -> None:
    assert ControllerConfig(key_freeze=value).key_freeze == "f"  # type: ignore[arg-type]


def test_a_key_shared_with_an_earlier_action_stays_with_that_action() -> None:
    cc = ControllerConfig(key_reset="f", key_freeze="f")
    assert cc.key_reset == "f"
    assert cc.key_freeze == ""


def test_a_save_that_binds_freeze_keeps_it_over_an_older_binding() -> None:
    cfg = AppConfig()
    apply_section_data(cfg, "keyboard", {"key_freeze": "x"})
    assert cfg.controller.key_freeze == "x"
    assert cfg.controller.key_reset == ""
    apply_section_data(cfg, "gamepad", {"btn_freeze": "START"})
    assert cfg.controller.btn_freeze == "START"
