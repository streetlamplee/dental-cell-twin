"""Rendered RGB frames from the inspection camera (Gate B).

A dedicated ViewportWindow renders the inspection camera at a fixed resolution.
Frames are pulled with capture_viewport_to_buffer and handed over as HxWx3 uint8
numpy arrays. Nothing here reads USD metadata about products.

Note (Kit 110.4): a bare ViewportWidget inside an omni.ui.Window never delivered
frames; a full ViewportWindow does (see scripts/probe_capture.ps1).
"""

import asyncio
import ctypes
import hashlib
import time
from typing import Callable, Optional, Tuple

import carb
import numpy as np
from omni.kit.viewport.utility import capture_viewport_to_buffer, create_viewport_window, next_viewport_frame_async

FrameCallback = Callable[[np.ndarray, float, bool], None]  # (rgb, capture_latency_ms, stale)

_get_pointer = ctypes.pythonapi.PyCapsule_GetPointer
_get_pointer.argtypes = [ctypes.py_object, ctypes.c_char_p]


def capsule_to_rgb(buffer, buffer_size: int, width: int, height: int, byte_format) -> np.ndarray:
    """Copy an RGBA8 capture buffer (PyCapsule) into an HxWx3 uint8 array."""
    if buffer_size != width * height * 4:
        raise ValueError(f"unexpected buffer size {buffer_size} for {width}x{height} ({byte_format})")
    _get_pointer.restype = ctypes.POINTER(ctypes.c_ubyte * buffer_size)
    raw = _get_pointer(buffer, None).contents
    rgba = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)
    return rgba[:, :, :3].copy()  # copy: the capture buffer is only valid inside the callback


class InspectionFrameProvider:
    WINDOW_TITLE = "VisionTwin Inspection Camera"
    # Stale-frame retry budget: 3 attempts x 3 frames (~0.15 s at 60 fps) keeps the product
    # inside the +-0.25 m inspection window at 0.5 m/s.
    MAX_ATTEMPTS = 3
    RETRY_FRAMES = 3

    def __init__(self, camera_path: Optional[str], resolution: Tuple[int, int]) -> None:
        w, h = resolution
        self._resolution = resolution
        self._window = create_viewport_window(self.WINDOW_TITLE, width=w // 2, height=h // 2 + 40,
                                              camera_path=camera_path)
        if self._window is None:
            raise RuntimeError("could not create the inspection viewport window")
        self._pending = 0
        self._last_digest = None
        self.last_attempts = 0

    async def ready_async(self) -> None:
        """Wait for the first rendered frames, then lock the resolution.
        Changing the resolution right after window creation crashed Kit 110.4 (2026-10-21)."""
        await next_viewport_frame_async(self.viewport_api, 3)
        self._lock_resolution()
        await next_viewport_frame_async(self.viewport_api, 3)

    def _lock_resolution(self) -> None:
        """Render at a fixed resolution, independent of the window size.
        The app sets viewport fillViewport=true, which would otherwise follow the UI size."""
        widget = self._window.viewport_widget
        widget.fill_frame = False
        widget.expand_viewport = False
        widget.set_resolution(self._resolution)

    @property
    def viewport_api(self):
        return self._window.viewport_api

    @property
    def pending(self) -> int:
        return self._pending

    def set_camera(self, camera_path: str) -> None:
        self.viewport_api.camera_path = camera_path

    def request_frame(self, on_frame: FrameCallback, on_error: Optional[Callable[[str], None]] = None) -> None:
        """Capture a frame rendered AFTER this request (non-blocking).

        on_frame(rgb, capture_latency_ms, stale): stale=True when the pixels are byte-identical
        to the previous capture, i.e. the viewport did not render a new image (seen once on
        2026-10-21: two products 1.5 s apart got the same frame).
        """
        t_request = time.perf_counter()
        self._pending += 1
        asyncio.ensure_future(self._capture_async(t_request, on_frame, on_error))

    async def _capture_async(self, t_request, on_frame, on_error):
        got = {}

        def _on_capture(buffer, buffer_size, width, height, byte_format):
            try:
                got["rgb"] = capsule_to_rgb(buffer, buffer_size, width, height, byte_format)
            except Exception as exc:  # report, never crash the render callback
                carb.log_error(f"[visiontwin.factory] frame conversion failed: {exc}")
                got["error"] = str(exc)

        try:
            await next_viewport_frame_async(self.viewport_api, 1)  # a frame newer than the request
            for attempt in range(1, self.MAX_ATTEMPTS + 1):
                got.clear()
                await capture_viewport_to_buffer(self.viewport_api, _on_capture).wait_for_result()
                if "error" in got or "rgb" not in got:
                    if on_error:
                        on_error(got.get("error", "no frame delivered"))
                    return
                digest = hashlib.md5(got["rgb"].tobytes()).digest()
                stale = digest == self._last_digest
                if not stale or attempt == self.MAX_ATTEMPTS:
                    break
                await next_viewport_frame_async(self.viewport_api, self.RETRY_FRAMES)
            self._last_digest = digest
            self.last_attempts = attempt
            on_frame(got["rgb"], (time.perf_counter() - t_request) * 1000.0, stale)
        finally:
            self._pending -= 1

    def destroy(self) -> None:
        if self._window:
            self._window.destroy()
            self._window = None
