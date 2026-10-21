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
import omni.kit.app
from omni.kit.viewport.utility import create_viewport_window, next_viewport_frame_async
from omni.kit.widget.viewport.capture import ByteCapture

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
    TIMEOUT_UPDATES = 180  # 3 s of simulation time at the default fixed step

    def __init__(self, camera_path: Optional[str], resolution: Tuple[int, int]) -> None:
        w, h = resolution
        self._resolution = resolution
        self._window = create_viewport_window(self.WINDOW_TITLE, width=w // 2, height=h // 2 + 40,
                                              camera_path=camera_path)
        if self._window is None:
            raise RuntimeError("could not create the inspection viewport window")
        self._pending = 0
        self._last_digest = None
        self.frame_target_misses = 0
        self.timeouts = 0

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
        t_request = time.perf_counter()
        target = omni.kit.app.get_app().get_update_number()
        self._pending += 1
        asyncio.ensure_future(self._capture_async(target, t_request, on_frame, on_error))

    async def _capture_async(self, target, t_request, on_frame, on_error):
        got = {}

        def _on_capture(buffer, buffer_size, width, height, byte_format):
            try:
                got["rgb"] = capsule_to_rgb(buffer, buffer_size, width, height, byte_format)
            except Exception as exc:  # report, never crash the render callback
                carb.log_error(f"[visiontwin.factory] frame conversion failed: {exc}")
                got["error"] = str(exc)

        try:
            cap = ByteCapture(_on_capture, aov_name="LdrColor", frame_to_capture=target,
                              viewport=self.viewport_api)
            self.viewport_api.schedule_capture(cap)
            waiter = asyncio.ensure_future(cap.wait_for_result())
            app = omni.kit.app.get_app()
            for _ in range(self.TIMEOUT_UPDATES):
                if waiter.done():
                    break
                await app.next_update_async()
            if not waiter.done():
                # Seen 2026-10-21: after 24 products the inspection viewport stopped reaching
                # the requested frame and captures waited forever. Give up, report, move on.
                waiter.cancel()
                self.timeouts += 1
                last = self.viewport_api.frame_info.get("swh_frame_number")
                msg = (f"capture timeout: frame {target} not rendered within {self.TIMEOUT_UPDATES} updates "
                       f"(viewport last swh={last}, now update={app.get_update_number()})")
                carb.log_warn(f"[visiontwin.factory] {msg}")
                if on_error:
                    on_error(msg)
                return
            if "rgb" not in got:
                self.frame_target_misses += 1
                if on_error:
                    on_error(got.get("error", f"frame {target} not captured"))
                return
            swh = (cap.frame_info or {}).get("swh_frame_number")
            frame_offset = None if swh is None else swh - target
            digest = hashlib.md5(got["rgb"].tobytes()).digest()
            stale = digest == self._last_digest
            self._last_digest = digest
            on_frame(got["rgb"], (time.perf_counter() - t_request) * 1000.0, stale, frame_offset)
        finally:
            self._pending -= 1

    def destroy(self) -> None:
        if self._window:
            self._window.destroy()
            self._window = None
