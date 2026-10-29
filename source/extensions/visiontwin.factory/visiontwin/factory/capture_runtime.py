"""Owned viewport capture requests with independent wall/update budgets and tombstones."""

import asyncio
import hashlib
import time

import carb
import omni.kit.app
from omni.kit.widget.viewport.capture import ByteCapture

from .core.runtime import TaskOwner


class CapturePool:
    def __init__(self, viewport, convert, wall_timeout_s=30.0, update_budget=180, delivery_delay_s=0.0):
        if wall_timeout_s <= 0 or update_budget <= 0 or delivery_delay_s < 0:
            raise ValueError("capture budgets must be positive and delivery delay nonnegative")
        self.viewport, self.convert = viewport, convert
        self.wall_timeout_s, self.update_budget = wall_timeout_s, update_budget
        self.delivery_delay_s = delivery_delay_s
        self.owner = TaskOwner()
        self.requests = {}
        self.sequence = 0
        self.closed = False
        self.last_digest = None
        self.timeouts = 0
        self.frame_target_misses = 0

    @property
    def pending(self):
        return len(self.requests)

    def request(self, on_frame, on_error=None, on_event=None):
        if self.closed:
            raise RuntimeError("capture pool closed")
        self.sequence += 1
        request = dict(id=self.sequence, terminal=False, notify=on_event,
                       native_scheduled=False, native_received=False,
                       target=omni.kit.app.get_app().get_update_number(), t0=time.perf_counter())
        self.requests[request["id"]] = request
        self.owner.create(self._capture(request, on_frame, on_error))

    def _finish(self, request, event, **detail):
        if request["terminal"]:
            return False
        request["terminal"] = True
        self.requests.pop(request["id"], None)
        if request["notify"]:
            request["notify"](event, **detail)
        return True

    def cancel_pending(self):
        for request in tuple(self.requests.values()):
            self._finish(request, "CANCELLED", detail="owner invalidated")
        self.owner.cancel()

    def close(self):
        self.closed = True
        self.cancel_pending()

    async def drain(self):
        await self.owner.drain()

    async def _capture(self, request, on_frame, on_error):
        got = {}
        waiter = None

        def received(buffer, size, width, height, fmt):
            request["native_received"] = True
            if request["terminal"] or self.closed:
                return  # native callback can outlive Python waiter cancellation
            try:
                got["rgb"] = self.convert(buffer, size, width, height, fmt)
            except Exception as exc:
                got["error"] = str(exc)

        try:
            if request["terminal"]:
                return
            viewport = self.viewport()
            cap = ByteCapture(received, aov_name="LdrColor", frame_to_capture=request["target"], viewport=viewport)
            viewport.schedule_capture(cap)
            request["native_scheduled"] = True
            waiter = asyncio.ensure_future(cap.wait_for_result())
            app = omni.kit.app.get_app()
            updates = 0
            reason = None
            while not request["terminal"]:
                elapsed = time.perf_counter() - request["t0"]
                # Deadlines take precedence over completion when both are observed together.
                if elapsed >= self.wall_timeout_s:
                    reason = "wall_timeout"
                    break
                if waiter.done() and elapsed >= self.delivery_delay_s:
                    await waiter  # propagate native capture errors
                    break
                if updates >= self.update_budget:
                    reason = "update_budget"
                    break
                await app.next_update_async()
                updates += 1
            if request["terminal"]:
                return
            if reason:
                self.timeouts += 1
                if self._finish(request, "TIMEOUT", detail=reason) and on_error:
                    on_error(reason)
                return
            if "rgb" not in got:
                self.frame_target_misses += 1
                message = got.get("error", "requested frame not captured")
                if self._finish(request, "CAPTURE_ERROR", detail=message) and on_error:
                    on_error(message)
                return
            frame = (cap.frame_info or {}).get("swh_frame_number")
            digest = hashlib.md5(got["rgb"].tobytes()).hexdigest()
            stale = digest == self.last_digest
            self.last_digest = digest
            if self._finish(request, "CAPTURE_RECEIVED", captured_frame=frame, digest=digest):
                on_frame(got["rgb"], (time.perf_counter()-request["t0"])*1000,
                         stale, None if frame is None else frame-request["target"])
        except asyncio.CancelledError:
            self._finish(request, "CANCELLED", detail="task cancelled")
            raise
        except Exception as exc:
            if self._finish(request, "CAPTURE_ERROR", detail=str(exc)):
                if on_error:
                    on_error(str(exc))
            else:
                carb.log_error(f"[visiontwin.factory] capture callback failed: {exc}")
                raise
        finally:
            if waiter is not None:
                if not waiter.done():
                    waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
            self._finish(request, "CANCELLED", detail="capture ended without delivery")
