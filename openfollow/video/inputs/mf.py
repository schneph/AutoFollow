# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 OpenFollow Project
"""Media Foundation (Windows USB camera / capture card) video input plugin.

Builds an ``mfvideosrc`` capture pipeline and persists the device's symbolic
link path (``device.path``), which stays the same across plug order changes.
Windows-only via ``is_available()``.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import Any

from openfollow.video.failure import SourceKind
from openfollow.video.inputs._base import (
    ConfigField,
    InputCapabilities,
    ReconnectPolicy,
    VideoInputBase,
    WebRoute,
    coerce_positive_int,
)

logger = logging.getLogger(__name__)

_MF_API = "mediafoundation"


def _discover_mf_devices() -> list[dict[str, str]]:
    """Enumerate Media Foundation video sources via ``Gst.DeviceMonitor``.

    Returns a list of dicts with keys: ``path``, ``name``. Empty off Windows
    so plugin contract tests elsewhere never scan real devices.
    """
    if sys.platform != "win32":
        return []
    try:
        from gi.repository import Gst
    except Exception:
        return []
    try:
        Gst.init(None)
        monitor = Gst.DeviceMonitor.new()
        monitor.add_filter("Video/Source", None)
        if not monitor.start():
            return []
        try:
            devices = monitor.get_devices() or []
        finally:
            monitor.stop()

        result: list[dict[str, str]] = []
        for dev in devices:
            props = dev.get_properties()
            if props is None:
                continue
            if (props.get_string("device.api") or "") != _MF_API:
                continue
            path = props.get_string("device.path") or ""
            if not path:
                continue
            result.append({"path": path, "name": dev.get_display_name() or path})
        return result
    except Exception as exc:
        logger.debug("Media Foundation device discovery failed: %s", exc)
        return []


class MfInput(VideoInputBase):
    """USB camera / capture card input via Media Foundation (Windows)."""

    input_id = "mf"
    display_name = "USB Camera (Windows)"
    source_element_name = "mfvideosrc"
    source_kind = SourceKind.LOCAL

    # -- Declarations ---------------------------------------------------

    @classmethod
    def config_fields(cls) -> list[ConfigField]:
        return [
            ConfigField("mf_device_path", str, "", "Device"),
            ConfigField("mf_width", int, 1280, "Width"),
            ConfigField("mf_height", int, 720, "Height"),
            ConfigField("mf_framerate", int, 30, "Framerate"),
        ]

    @classmethod
    def capabilities(cls) -> InputCapabilities:
        return InputCapabilities(
            has_source_discovery=True,
            has_source_selection=True,
            selection_title="SELECT USB CAMERA",
            force_zero_latency=True,
        )

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "Media Foundation is Windows-only"
        try:
            from gi.repository import Gst

            Gst.init(None)
            if Gst.ElementFactory.find("mfvideosrc") is None:
                return False, "mfvideosrc GStreamer element not found – install gst-plugins-bad"
        except Exception:
            return False, "GStreamer not available"
        return True, ""

    @classmethod
    def reconnect_policy(cls) -> ReconnectPolicy:
        return ReconnectPolicy(
            max_attempts=3,
            min_delay=1.0,
            max_delay=5.0,
            backoff_multiplier=2.0,
            connection_timeout=5.0,
            fallback_to_selection=True,
        )

    # -- Pipeline -------------------------------------------------------

    def create_pipeline(
        self,
        config: dict[str, Any],
        sink: Any,
        build_overlay_tail: Callable[..., Any],
        prepare_sink: Callable[..., Any],
    ) -> Any:
        """Build a Media Foundation capture pipeline.

        ``mfvideosrc -> capsfilter -> decodebin -> queue -> videoconvert
        -> [overlay tail] -> sink``

        The capsfilter accepts raw video or MJPEG at the requested mode:
        most webcams only offer their full resolution as MJPEG over USB 2,
        and ``decodebin`` passes raw frames straight through.
        """
        from gi.repository import Gst

        device_path = str(config.get("mf_device_path", "") or "")
        width = coerce_positive_int(config.get("mf_width", 1280), 1280)
        height = coerce_positive_int(config.get("mf_height", 720), 720)
        framerate = coerce_positive_int(config.get("mf_framerate", 30), 30)

        def make(kind: str, name: str) -> Any:
            elem = Gst.ElementFactory.make(kind, name)
            if elem is None:
                raise RuntimeError(f"{kind} GStreamer element not found – install gst-plugins-base/good")
            return elem

        pipeline = Gst.Pipeline.new("mf-sink")

        src = Gst.ElementFactory.make("mfvideosrc", "mfvideosrc")
        if src is None:
            raise RuntimeError("mfvideosrc GStreamer element not found – install gst-plugins-bad")
        if device_path:
            src.set_property("device-path", device_path)
        logger.info("Media Foundation source: %s", device_path or "<default>")

        mode = f"width=(int){width},height=(int){height},framerate=(fraction){framerate}/1"
        caps_str = f"video/x-raw,{mode};image/jpeg,{mode}"
        capsfilter = make("capsfilter", "capsfilter")
        capsfilter.set_property("caps", Gst.Caps.from_string(caps_str))
        logger.info("Media Foundation caps: %s", caps_str)

        decodebin = make("decodebin", "decodebin")

        queue = make("queue", "post_queue")
        queue.set_property("max-size-buffers", 2)
        queue.set_property("max-size-bytes", 0)
        queue.set_property("max-size-time", 0)
        queue.set_property("leaky", 2)

        convert = make("videoconvert", "convert")

        sink = prepare_sink()
        if sink is None:
            raise RuntimeError("No video sink available for Media Foundation pipeline")

        for elem in (src, capsfilter, decodebin, queue, convert, sink):
            pipeline.add(elem)

        if not src.link(capsfilter):
            raise RuntimeError("Failed to link mfvideosrc -> capsfilter")
        if not capsfilter.link(decodebin):
            raise RuntimeError("Failed to link capsfilter -> decodebin")
        if not queue.link(convert):
            raise RuntimeError("Failed to link queue -> videoconvert")

        def on_pad_added(_element: Any, pad: Any) -> None:
            sink_pad = queue.get_static_pad("sink")
            if sink_pad is None or sink_pad.is_linked():
                return
            caps = pad.get_current_caps() or pad.query_caps(None)
            caps_str = caps.to_string() if caps else ""
            if not caps_str.startswith("video/"):
                return
            result = pad.link(sink_pad)
            if result != Gst.PadLinkReturn.OK:
                logger.error("Failed to link decodebin pad %s: %s", pad.get_name(), result)

        decodebin.connect("pad-added", on_pad_added)
        build_overlay_tail(pipeline, convert, sink)
        return pipeline

    # -- Lifecycle hooks ------------------------------------------------

    def on_bus_async_done(self, pipeline: Any) -> None:
        """Local device: force zero latency."""
        pipeline.set_latency(0)
        logger.info("Pipeline ASYNC_DONE (Media Foundation) – latency forced to 0")

    # -- Source discovery -----------------------------------------------

    @classmethod
    def discover_sources(cls, timeout: float = 2.0) -> list[str]:
        """Return Media Foundation camera device paths."""
        return [d["path"] for d in _discover_mf_devices()]

    # -- Web UI ---------------------------------------------------------

    @classmethod
    def web_ui_html(cls, config: dict[str, Any]) -> str:
        device_path = cls._esc(config.get("mf_device_path", ""))
        width = cls._esc(config.get("mf_width", 1280))
        height = cls._esc(config.get("mf_height", 720))
        framerate = cls._esc(config.get("mf_framerate", 30))
        return (
            '<div class="row ndi-row">'
            '    <div class="field wide">'
            "        <label>Device</label>"
            '        <select name="mf_device_path"'
            '                hx-get="/video-input/mf/devices"'
            '                hx-trigger="load, click from:#refresh-mf"'
            '                hx-target="this"'
            '                hx-swap="innerHTML">'
            f'            <option value="{device_path}">'
            f"              {device_path or '-- Loading... --'}"
            "            </option>"
            "        </select>"
            "    </div>"
            '    <button type="button" id="refresh-mf"'
            '            class="secondary"'
            '            style="margin-bottom:0;">'
            "Scan</button>"
            "</div>"
            '<div class="row">'
            '    <div class="field">'
            "        <label>Width</label>"
            f'        <input type="number" name="mf_width" value="{width}" min="160" max="3840">'
            "    </div>"
            '    <div class="field">'
            "        <label>Height</label>"
            f'        <input type="number" name="mf_height" value="{height}" min="120" max="2160">'
            "    </div>"
            '    <div class="field">'
            "        <label>FPS</label>"
            f'        <input type="number" name="mf_framerate" value="{framerate}" min="1" max="120">'
            "    </div>"
            "</div>"
        )

    @classmethod
    def web_routes(cls) -> list[WebRoute]:
        return [WebRoute("GET", "/video-input/mf/devices", "handle_list_devices")]

    def handle_list_devices(self, config: dict[str, Any]) -> str:
        """Return ``<option>`` elements for the device dropdown."""
        devices = _discover_mf_devices()
        current = config.get("mf_device_path", "")

        options: list[str] = []
        if not devices:
            options.append('<option value="">-- No devices found --</option>')
        for dev in devices:
            path = self._esc(dev["path"])
            name = self._esc(dev["name"])
            sel = " selected" if dev["path"] == current else ""
            options.append(f'<option value="{path}"{sel}>{name}</option>')
        return "\n".join(options)

    # -- Config ---------------------------------------------------------

    @classmethod
    def get_source_label(cls, config: dict[str, Any]) -> str:
        # Side-effect free: no device scan here.
        width = config.get("mf_width", 1280)
        height = config.get("mf_height", 720)
        framerate = config.get("mf_framerate", 30)
        name = "camera" if config.get("mf_device_path") else "default camera"
        return f"{name} ({width}x{height}@{framerate})"
