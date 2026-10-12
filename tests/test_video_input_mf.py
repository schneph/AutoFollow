# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Tests for the Media Foundation (Windows USB camera) video input plugin."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from openfollow.video.inputs import mf as mf_module
from openfollow.video.inputs.mf import MfInput, _discover_mf_devices
from tests._fake_gst import FakeElement, FakePad, FakePipeline, make_fake_gst

pytestmark = pytest.mark.unit


class _FakeProps:
    def __init__(self, mapping: dict[str, str]) -> None:
        self._m = mapping

    def get_string(self, key: str) -> str | None:
        return self._m.get(key)


class _FakeDevice:
    def __init__(self, *, props: dict[str, str] | None, display_name: str = "") -> None:
        self._props = _FakeProps(props) if props is not None else None
        self._name = display_name

    def get_properties(self) -> _FakeProps | None:
        return self._props

    def get_display_name(self) -> str:
        return self._name


class _FakeMonitor:
    def __init__(self, devices: list[_FakeDevice], *, start_ok: bool = True) -> None:
        self._devices = devices
        self._start_ok = start_ok
        self.filters: list[tuple[str, object]] = []

    def add_filter(self, classification: str, caps: object) -> None:
        self.filters.append((classification, caps))

    def start(self) -> bool:
        return self._start_ok

    def stop(self) -> None:
        pass

    def get_devices(self) -> list[_FakeDevice]:
        return list(self._devices)


def _fake_gst_with_devices(devices: list[_FakeDevice], *, start_ok: bool = True):
    fake = make_fake_gst()

    class _DeviceMonitorNs:
        @staticmethod
        def new() -> _FakeMonitor:
            return _FakeMonitor(devices, start_ok=start_ok)

    fake.DeviceMonitor = _DeviceMonitorNs  # type: ignore[attr-defined]
    return fake


def _mf_device(path: str, name: str) -> _FakeDevice:
    return _FakeDevice(props={"device.api": "mediafoundation", "device.path": path}, display_name=name)


class TestMfRegistration:
    def test_identity(self) -> None:
        assert MfInput.input_id == "mf"
        assert MfInput.display_name == "USB Camera (Windows)"
        assert MfInput.source_element_name == "mfvideosrc"

    def test_in_registry(self) -> None:
        from openfollow.video.inputs import get_registry

        assert "mf" in get_registry()


class TestMfConfig:
    def test_config_fields_and_defaults(self) -> None:
        fields = {f.name: f.default for f in MfInput.config_fields()}
        assert fields == {"mf_device_path": "", "mf_width": 1280, "mf_height": 720, "mf_framerate": 30}

    def test_app_config_carries_every_field(self) -> None:
        from openfollow.configuration import AppConfig

        cfg = AppConfig()
        for field in MfInput.config_fields():
            assert getattr(cfg, field.name) == field.default

    def test_config_changed(self) -> None:
        from openfollow.configuration import AppConfig

        old = AppConfig()
        assert MfInput.config_changed(old, old) is False
        assert MfInput.config_changed(old, AppConfig(mf_device_path="\\\\?\\usb#cam")) is True
        assert MfInput.config_changed(old, AppConfig(mf_width=1920, mf_height=1080)) is True


class TestMfCapabilities:
    def test_discovery_and_selection(self) -> None:
        caps = MfInput.capabilities()
        assert caps.has_source_discovery is True
        assert caps.has_source_selection is True
        assert caps.force_zero_latency is True

    def test_reconnect_policy_falls_back_to_selection(self) -> None:
        policy = MfInput.reconnect_policy()
        assert policy.max_attempts == 3
        assert policy.fallback_to_selection is True


class TestMfIsAvailable:
    def test_unavailable_off_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        ok, reason = MfInput.is_available()
        assert ok is False
        assert "Windows" in reason

    def test_unavailable_when_factory_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        with patch("gi.repository.Gst", make_fake_gst()):
            ok, reason = MfInput.is_available()
        assert ok is False
        assert "mfvideosrc" in reason

    def test_available_with_factory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        with patch("gi.repository.Gst", make_fake_gst(known_factories={"mfvideosrc": object()})):
            assert MfInput.is_available() == (True, "")

    def test_unavailable_when_gst_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")

        class _BoomGst:
            @staticmethod
            def init(_):
                raise RuntimeError("gst boom")

        with patch("gi.repository.Gst", _BoomGst):
            ok, reason = MfInput.is_available()
        assert ok is False
        assert "GStreamer not available" in reason


class TestDiscoverMfDevices:
    def test_off_windows_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        assert _discover_mf_devices() == []

    def test_gi_import_failure_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import builtins

        monkeypatch.setattr(sys, "platform", "win32")
        real_import = builtins.__import__

        def _fail_gi(name, *args, **kwargs):
            if name.startswith("gi.repository"):
                raise ImportError("no gi here")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fail_gi)
        assert _discover_mf_devices() == []

    def test_monitor_start_failure_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        with patch("gi.repository.Gst", _fake_gst_with_devices([], start_ok=False)):
            assert _discover_mf_devices() == []

    def test_keeps_only_media_foundation_devices_with_a_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        devices = [
            _FakeDevice(props=None, display_name="ghost"),
            _FakeDevice(props={"device.api": "dshow", "device.path": "x"}, display_name="DirectShow"),
            _FakeDevice(props={"device.api": "mediafoundation"}, display_name="pathless"),
            _mf_device("usb#cam1", "Logitech C920"),
            _mf_device("usb#cam2", ""),
        ]
        with patch("gi.repository.Gst", _fake_gst_with_devices(devices)):
            assert _discover_mf_devices() == [
                {"path": "usb#cam1", "name": "Logitech C920"},
                {"path": "usb#cam2", "name": "usb#cam2"},
            ]

    def test_gst_init_failure_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")

        class _BoomGst:
            @staticmethod
            def init(_):
                raise RuntimeError("registry corrupted")

        with patch("gi.repository.Gst", _BoomGst):
            assert _discover_mf_devices() == []


def _build(config=None, *, fake=None, prepare_sink=None) -> FakePipeline:
    from gi.repository import Gst  # noqa: F401

    sink = FakeElement("shared_videosink")
    with patch("gi.repository.Gst", fake or make_fake_gst()):
        return MfInput().create_pipeline(
            config=config or {},
            sink=sink,
            build_overlay_tail=lambda *a: None,
            prepare_sink=prepare_sink or (lambda: sink),
        )


class TestMfPipeline:
    def test_builds_chain_with_device_path_and_caps(self) -> None:
        pipeline = _build({"mf_device_path": "usb#cam1", "mf_width": 1920, "mf_height": 1080, "mf_framerate": 60})
        assert pipeline.get_by_name("mfvideosrc").properties["device-path"] == "usb#cam1"
        caps = pipeline.get_by_name("capsfilter").properties["caps"].to_string()
        mode = "width=(int)1920,height=(int)1080,framerate=(fraction)60/1"
        assert caps == f"video/x-raw,{mode};image/jpeg,{mode}"
        for name in ("decodebin", "post_queue", "convert", "shared_videosink"):
            assert pipeline.get_by_name(name) is not None

    def test_blank_device_path_leaves_default_camera(self) -> None:
        pipeline = _build({})
        assert "device-path" not in pipeline.get_by_name("mfvideosrc").properties

    def test_degenerate_mode_falls_back_to_defaults(self) -> None:
        pipeline = _build({"mf_width": 0, "mf_height": -5, "mf_framerate": "x"})
        caps = pipeline.get_by_name("capsfilter").properties["caps"].to_string()
        assert caps.startswith("video/x-raw,width=(int)1280,height=(int)720,framerate=(fraction)30/1;")

    def test_missing_mfvideosrc_raises(self) -> None:
        with pytest.raises(RuntimeError, match="mfvideosrc"):
            _build(fake=make_fake_gst(missing_elements={"mfvideosrc"}))

    @pytest.mark.parametrize("missing", ["capsfilter", "decodebin", "queue", "videoconvert"])
    def test_missing_chain_element_raises(self, missing: str) -> None:
        with pytest.raises(RuntimeError, match=f"{missing} GStreamer element not found"):
            _build(fake=make_fake_gst(missing_elements={missing}))

    def test_no_sink_raises(self) -> None:
        with pytest.raises(RuntimeError, match="No video sink"):
            _build(prepare_sink=lambda: None)

    @pytest.mark.parametrize(
        ("kind", "match"),
        [("mfvideosrc", "mfvideosrc"), ("capsfilter", "capsfilter"), ("queue", "queue")],
    )
    def test_link_failure_raises(self, kind: str, match: str) -> None:
        with pytest.raises(RuntimeError, match=match):
            _build(fake=make_fake_gst(link_fail_kinds={kind}))

    def test_on_bus_async_done_forces_zero_latency(self) -> None:
        pipeline = FakePipeline("mf")
        MfInput().on_bus_async_done(pipeline)
        assert pipeline.latency_values == [0]


class TestMfDecodebinPads:
    def _pad_added(self):
        pipeline = _build({})
        decodebin = pipeline.get_by_name("decodebin")
        queue = pipeline.get_by_name("post_queue")
        (callback,) = [cb for sig, cb in decodebin.signals if sig == "pad-added"]
        return callback, queue

    def test_first_video_pad_links_to_queue(self) -> None:
        callback, queue = self._pad_added()
        pad = FakePad("src_0")
        with patch("gi.repository.Gst", make_fake_gst()):
            callback(None, pad)
        assert pad.linked_to is queue.get_static_pad("sink")

    def test_non_video_pad_is_ignored(self) -> None:
        callback, queue = self._pad_added()

        class _AudioPad(FakePad):
            def get_current_caps(self):
                from tests._fake_gst import FakeCaps

                return FakeCaps("audio/x-raw")

        pad = _AudioPad("src_1")
        with patch("gi.repository.Gst", make_fake_gst()):
            callback(None, pad)
        assert pad.linked_to is None
        assert queue.get_static_pad("sink").is_linked() is False

    def test_second_video_pad_is_ignored(self) -> None:
        callback, _queue = self._pad_added()
        with patch("gi.repository.Gst", make_fake_gst()):
            callback(None, FakePad("src_0"))
            extra = FakePad("src_1")
            callback(None, extra)
        assert extra.linked_to is None

    def test_refused_link_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        callback, _queue = self._pad_added()
        with patch("gi.repository.Gst", make_fake_gst()):
            callback(None, FakePad("src_0", link_returns="refused"))
        assert "Failed to link decodebin pad src_0" in caplog.text


class TestMfWebUI:
    def test_html_carries_fields_and_device_route(self) -> None:
        html = MfInput.web_ui_html({"mf_device_path": "usb#cam1", "mf_width": 1920})
        for name in ("mf_device_path", "mf_width", "mf_height", "mf_framerate", "/video-input/mf/devices"):
            assert name in html
        assert 'value="1920"' in html

    def test_html_escapes_device_path(self) -> None:
        html = MfInput.web_ui_html({"mf_device_path": '"><script>'})
        assert "<script>" not in html

    def test_web_routes_declared(self) -> None:
        (route,) = MfInput.web_routes()
        assert route.path == "/video-input/mf/devices"

    def test_list_devices_without_devices(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mf_module, "_discover_mf_devices", lambda: [])
        assert "-- No devices found --" in MfInput().handle_list_devices({})

    def test_list_devices_selects_current_and_escapes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            mf_module,
            "_discover_mf_devices",
            lambda: [{"path": "usb#a", "name": "<evil>"}, {"path": "usb#b", "name": "C920"}],
        )
        html = MfInput().handle_list_devices({"mf_device_path": "usb#b"})
        assert 'value="usb#b" selected>C920' in html
        assert 'value="usb#a">&lt;evil&gt;' in html

    def test_discover_sources_returns_paths(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mf_module, "_discover_mf_devices", lambda: [{"path": "usb#a", "name": "A"}])
        assert MfInput.discover_sources() == ["usb#a"]


class TestMfSourceLabel:
    def test_label_names_mode(self) -> None:
        label = MfInput.get_source_label({"mf_device_path": "usb#a", "mf_width": 1920, "mf_height": 1080})
        assert label == "camera (1920x1080@30)"

    def test_label_without_device(self) -> None:
        assert MfInput.get_source_label({}) == "default camera (1280x720@30)"

    def test_label_does_not_scan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mf_module, "_discover_mf_devices", lambda: pytest.fail("must not scan"))
        MfInput.get_source_label({"mf_device_path": "usb#a"})
