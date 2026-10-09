# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""The privilege modules the web UI imports load on a host with no user database (Windows)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

import openfollow.privilege

pytestmark = pytest.mark.unit

_PRIVILEGE_DIR = Path(openfollow.privilege.__file__).parent


@pytest.mark.parametrize(
    ("module", "names"),
    [("settings_backup", ("pwd",)), ("device_repair", ("grp", "pwd"))],
)
def test_module_imports_without_pwd_and_grp(monkeypatch, module: str, names: tuple[str, ...]) -> None:
    monkeypatch.setitem(sys.modules, "pwd", None)
    monkeypatch.setitem(sys.modules, "grp", None)
    spec = importlib.util.spec_from_file_location(f"_no_userdb_{module}", _PRIVILEGE_DIR / f"{module}.py")
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, loaded)
    spec.loader.exec_module(loaded)

    assert all(getattr(loaded, name) is None for name in names)
