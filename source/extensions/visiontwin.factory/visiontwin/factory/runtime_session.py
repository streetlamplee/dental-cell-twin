"""Kit run generation, stage ownership and optional trace integration."""

import asyncio
import json
import os
import weakref

import carb.eventdispatcher
import omni.kit.app
import omni.usd

from .core.runtime import RunTrace, TaskOwner


class RuntimeSession:
    def __init__(self, extension):
        self.ext = weakref.proxy(extension)
        self.generation = 0
        self.alive = True
        self.changing_stage = False
        self.building = False
        self.tasks = TaskOwner(on_error=lambda msg: carb.log_error(f"[visiontwin.factory] owned task failed: {msg}"))
        self.trace = None
        self.active_ticket = None
        self.discarded = 0
        ctx = omni.usd.get_context()
        self.stage_observer = carb.eventdispatcher.get_eventdispatcher().observe_event(
            observer_name="visiontwin.factory.stage_closing",
            event_name=ctx.stage_event_name(omni.usd.StageEventType.CLOSING), on_event=self._stage_closing)

    def valid(self, generation):
        return self.alive and generation == self.generation

    def _stage_closing(self, _event):
        if self.changing_stage or not self.alive:
            return
        self.invalidate("stage_closing")
        ext = self.ext
        ext.stop()
        ext._scene_ready = False
        ext._destroy_frame_provider()
        ext._cell = ext._arm = None

    def invalidate(self, reason):
        self.generation += 1  # tombstone callbacks before closing logs or UI resources
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
        self.tasks.cancel(exclude=current_task)
        ext = self.ext
        frames = getattr(ext, "_frames", None)
        if frames is not None:
            frames.cancel_pending()
        trace, self.trace = self.trace, None
        if trace and not trace.closed:
            trace.close(ext._sim.time, status=f"aborted:{reason}")
            if getattr(ext, "run_dir", None):
                with open(os.path.join(ext.run_dir, "aborted.json"), "w", encoding="utf-8") as f:
                    json.dump(dict(reason=reason, generation=trace.generation, sim_s=ext._sim.time), f, indent=2)
        events = getattr(ext, "_events", None)
        if events is not None:
            events.close()
            ext._events = None
        ext._log = None
        ext._vision_setup_pending = False

    def shutdown(self):
        self.alive = False
        self.invalidate("shutdown")
        if self.stage_observer:
            self.stage_observer.reset()
            self.stage_observer = None

    def open(self, directory, run_id, enabled):
        self.trace = RunTrace(directory, run_id, self.generation, enabled)

    def mark(self, event, ticket=None, **details):
        if self.trace:
            self.trace.event(event, ticket or self.active_ticket, self.ext._sim.time,
                             omni.kit.app.get_app().get_update_number(), **details)

    def capture(self, product_id, view, on_frame, on_error):
        ext = self.ext
        generation, trace = self.generation, self.trace
        request_sim_s = ext._sim.time
        request_update = omni.kit.app.get_app().get_update_number()
        ticket = trace.request(product_id, view, request_sim_s, request_update) if trace else None

        def notify(event, **details):
            if trace and not trace.closed:
                live = self.valid(generation)
                # Kit may clear an unloaded IExt object's attributes even while callbacks retain it.
                trace.event(event, ticket, ext._sim.time if live else request_sim_s,
                            omni.kit.app.get_app().get_update_number() if live else request_update, **details)

        def guarded(callback):
            def call(*args):
                if not self.valid(generation):
                    self.discarded += 1
                    notify("DISCARDED", detail="invalid generation")
                    return
                previous, self.active_ticket = self.active_ticket, ticket
                try:
                    callback(*args)
                finally:
                    self.active_ticket = previous
            return call
        ext._frames.request_frame(guarded(on_frame), guarded(on_error), on_event=notify)
