"""Rendered RGB frames from the inspection camera (Gate B).

A dedicated ViewportWindow renders the inspection camera at a fixed resolution.
Frames are pulled with capture_viewport_to_buffer and handed over as HxWx3 uint8
numpy arrays. Nothing here reads USD metadata about products.

Note (Kit 110.4): a bare ViewportWidget inside an omni.ui.Window never delivered
frames; a full ViewportWindow does (see scripts/probe_capture.ps1).
"""

import ctypes
from typing import Callable, Optional, Tuple

import carb
import carb.settings
import numpy as np
import omni.kit.app
from omni.kit.viewport.utility import create_viewport_window, next_viewport_frame_async
from .capture_runtime import CapturePool

FrameCallback = Callable[[np.ndarray, float, bool, Optional[int]], None]  # (rgb, latency_ms, stale, frame_offset)

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
    TIMEOUT_UPDATES = 180  # app updates; not a wall-clock timeout or a simulation clock

    def __init__(self, camera_path: Optional[str], resolution: Tuple[int, int]) -> None:
        w, h = resolution
        self._resolution = resolution
        self._window = create_viewport_window(self.WINDOW_TITLE, width=w // 2, height=h // 2 + 40,
                                              camera_path=camera_path)
        if self._window is None:
            raise RuntimeError("could not create the inspection viewport window")
        settings = carb.settings.get_settings()
        def setting(name, default):
            value = settings.get(f"/exts/visiontwin.factory/{name}")
            return default if value is None else value
        self._pool = CapturePool(lambda: self.viewport_api, capsule_to_rgb,
            wall_timeout_s=float(setting("captureWallTimeoutS", 30.0)),
            update_budget=int(setting("captureUpdateBudget", self.TIMEOUT_UPDATES)),
            delivery_delay_s=float(setting("captureDeliveryDelayS", 0.0)))

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
        return self._pool.pending

    @property
    def frame_target_misses(self):
        return self._pool.frame_target_misses

    @property
    def timeouts(self):
        return self._pool.timeouts

    def set_camera(self, camera_path: str) -> None:
        self.viewport_api.camera_path = camera_path

    def request_frame(self, on_frame: FrameCallback, on_error: Optional[Callable[[str], None]] = None,
                      on_event=None) -> None:
        """Capture the frame that renders the CURRENT update's stage state (non-blocking).

        The target is the current app update number used as the SWH frame number
        (frame_to_capture), so the image shows the product exactly where the simulation put
        it this update, independent of render lag. With async rendering the captured frame
        trailed the simulation by ~70 updates (2026-10-21).

        on_frame(rgb, capture_latency_ms, stale, frame_offset):
          stale=True when the pixels are byte-identical to the previous capture;
          frame_offset = captured SWH frame - requested frame (0 = the requested state;
          None = unknown). Anything but 0 means the image may not show the requested product.
        """
        self._pool.request(on_frame, on_error, on_event)

    def cancel_pending(self):
        self._pool.cancel_pending()
        self._pool.last_digest = None

    async def drain(self):
        await self._pool.drain()

    def destroy(self) -> None:
        self._pool.close()
        if self._window:
            self._window.destroy()
            self._window = None
