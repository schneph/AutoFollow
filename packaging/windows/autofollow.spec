# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""PyInstaller spec for the Windows build, frozen from an MSYS2 UCRT64 Python.

Invoked by ``.github/workflows/windows.yml``. Shares the launcher and runtime hook
with the macOS bundle; the GTK / GStreamer / GObject stack comes from MSYS2.
"""

import importlib.util
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

REPO = Path(SPECPATH).resolve().parents[1]  # noqa: F821
MACOS = REPO / "packaging" / "macos"
WINDOWS = REPO / "packaging" / "windows"
BUILD = WINDOWS / "_build"

datas = []
binaries = []
hiddenimports = [
    "gi",
    "gi.repository.GLib",
    "gi.repository.GObject",
    "gi.repository.Gio",
    "gi.repository.Gtk",
    "gi.repository.Gdk",
    "gi.repository.GdkPixbuf",
    "gi.repository.Gst",
    "gi.repository.GstApp",
    "gi.repository.GstVideo",
    "gi.repository.Rsvg",
    "cairo",
    "cv2",
    "numpy",
]


def _add(triple):
    d, b, h = triple
    datas.extend(d)
    binaries.extend(b)
    hiddenimports.extend(h)


for pkg in ("gi", "cairo", "onnxruntime"):
    _add(collect_all(pkg))

# collect_all misses onnxruntime's pybind extension under MSYS2's ABI-tagged
# suffix, so ship everything in capi/ verbatim beside the package.
_ort = importlib.util.find_spec("onnxruntime")
if _ort is None or not _ort.submodule_search_locations:
    raise SystemExit("autofollow.spec: onnxruntime is not installed")
_capi = Path(next(iter(_ort.submodule_search_locations))) / "capi"
_ort_native = sorted(p for p in _capi.iterdir() if p.suffix.lower() in (".pyd", ".dll"))
if not any("pybind11_state" in p.name for p in _ort_native):
    raise SystemExit(f"autofollow.spec: no onnxruntime pybind extension in {_capi}")
binaries += [(str(p), "onnxruntime/capi") for p in _ort_native]
hiddenimports.append("onnxruntime.capi.onnxruntime_pybind11_state")
print(f"[autofollow.spec] onnxruntime native files: {[p.name for p in _ort_native]}")

try:
    datas += copy_metadata("openfollow")
except Exception:  # noqa: BLE001
    pass

# Package data plus every submodule: video inputs are discovered by walking the
# package and the web templates import submodules at render time.
datas += collect_data_files("openfollow")
hiddenimports += collect_submodules("openfollow")
hiddenimports += collect_submodules("mido.backends")

datas += [(str(WINDOWS / "config.seed.toml"), ".")]
for _model in sorted((BUILD / "models").glob("*.onnx")):
    datas += [(str(_model), "models")]

a = Analysis(  # noqa: F821
    [str(MACOS / "launcher.py")],
    pathex=[str(REPO)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    runtime_hooks=[str(MACOS / "runtime_hook.py")],
    excludes=["torch", "torchvision", "ultralytics", "matplotlib", "tkinter"],
    noarchive=False,
)

# NDI needs the proprietary SDK; never ship its plugin.
a.binaries = [b for b in a.binaries if "gstndi" not in os.path.basename(b[0]).lower()]

_gst = sorted(os.path.basename(b[0]) for b in a.binaries if "gst_plugins" in b[0].replace("\\", "/"))
print(f"[autofollow.spec] gst plugins kept: {len(_gst)}")
for _critical in ("libgstgtk.dll", "libgstmediafoundation.dll", "libgstvideoconvertscale.dll", "libgstplayback.dll"):
    if _critical not in _gst:
        raise SystemExit(f"autofollow.spec: critical gst plugin {_critical} was not collected")

pyz = PYZ(a.pure)  # noqa: F821

_icon = BUILD / "AutoFollow.ico"

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoFollow",
    console=False,
    upx=False,
    icon=str(_icon) if _icon.is_file() else None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    upx=False,
    name="AutoFollow",
)
