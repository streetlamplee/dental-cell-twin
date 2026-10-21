"""VisionTwin factory extension: wires the conveyor simulation to the USD stage, the
inspection camera and the UI."""

import asyncio
import json
import os
import time

import carb
import carb.eventdispatcher
import carb.settings
import carb.tokens
import omni.ext
import omni.kit.app
import omni.usd
from omni.kit.viewport.utility import get_active_viewport

from . import scene_manager as scene
from .core import layout as L
from .core.camera_model import inspection_roi
from .core.conveyor import EXIT, INSPECT, REJECT, SPAWN, ConveyorConfig, ConveyorSim
from .core.inspection_log import InspectionLog, InspectionRecord
from .core.product_tracker import ProductState
from .core.vision_inspector import UNKNOWN, InspectorConfig, VisionInspector
from .dashboard import Dashboard

LOG_PREFIX = "[visiontwin.factory]"
SETTINGS = "/exts/visiontwin.factory"

_instance = None


def get_instance():
    """The running extension, for automation scripts (e.g. scripts/render_smoke.py)."""
    return _instance


def _setting(name, default):
    value = carb.settings.get_settings().get(f"{SETTINGS}/{name}")
    return default if value is None or value == "" else value


def _resolve(path: str) -> str:
    return os.path.normpath(carb.tokens.get_tokens_interface().resolve(path))


class VisionTwinFactoryExtension(omni.ext.IExt):
    def on_startup(self, _ext_id):
        global _instance
        _instance = self
        carb.log_info(f"{LOG_PREFIX} startup")
        self._sim = ConveyorSim(self._conveyor_config(), reject_decider=lambda _p: False)
        self._update_sub = None
        self._scene_ready = False
        self._frames = None  # InspectionFrameProvider, only when a viewport exists
        self._main_viewport = None
        self._inspector = None
        self._log = None  # InspectionLog for the current run
        self.run_dir = None
        self._ui = Dashboard(
            on_build=self._on_build,
            on_start=self.start,
            on_stop=self.stop,
            on_reset=self.reset,
            on_speed=self._sim.set_speed,
            initial_speed=self._sim.config.speed,
        )

    def on_shutdown(self):
        global _instance
        _instance = None
        carb.log_info(f"{LOG_PREFIX} shutdown")
        self._unsubscribe()
        self._destroy_frame_provider()
        if self._ui:
            self._ui.destroy()
            self._ui = None

    # -- public API (UI buttons and automation scripts) ---------------------

    @property
    def pending_frames(self) -> int:
        return self._frames.pending if self._frames else 0

    def _on_build(self):
        asyncio.ensure_future(self.build_scene_async())

    @property
    def main_viewport(self):
        """The main (overview) viewport. Remembered before the inspection window exists,
        because get_active_viewport() may return the inspection window afterwards."""
        if self._main_viewport is None:
            self._main_viewport = get_active_viewport()
        return self._main_viewport

    async def build_scene_async(self):
        self.stop()
        main = self.main_viewport
        # Order matters (2026-10-21):
        #  - creating the inspection viewport BEFORE new_stage left the main viewport
        #    rendering nothing, so it is (re)created after the scene exists;
        #  - creating it while RTX still initialises crashed D3D, so wait for main frames.
        self._destroy_frame_provider()
        self._ui.set_status("creating new stage...")
        ctx = omni.usd.get_context()
        await ctx.new_stage_async()
        scene.build_factory_scene(ctx.get_stage())
        self._sim.config = self._conveyor_config()
        self._sim.reset()
        self._log = None
        await omni.kit.app.get_app().next_update_async()
        if main is not None:
            main.camera_path = L.OVERVIEW_CAMERA_PATH  # deterministic framing
        await self._create_frame_provider_async(main)
        await self._setup_inspection_async()
        self._scene_ready = True
        self._ui.set_status("scene ready")
        self._refresh_counters()
        print(f"{LOG_PREFIX} factory scene built")

    def start(self):
        if not self._scene_ready:
            self._ui.set_status("build the scene first")
            return
        if self._log is None and self._inspector is not None:
            self._open_run()
        self._sim.start()
        if self._update_sub is None:
            self._update_sub = carb.eventdispatcher.get_eventdispatcher().observe_event(
                event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
                on_event=self._on_update,
                observer_name="visiontwin.factory.update",
            )
        self._ui.set_status("running")
        print(f"{LOG_PREFIX} start")

    def stop(self):
        self._sim.stop()
        self._unsubscribe()
        if self._ui:
            self._ui.set_status("stopped")
        print(f"{LOG_PREFIX} stop")

    def reset(self):
        self.stop()
        self._sim.config = self._conveyor_config()
        self._sim.reset()
        self._log = None
        stage = omni.usd.get_context().get_stage()
        if self._scene_ready and stage:
            scene.clear_products(stage)
        self._ui.set_status("reset")
        self._ui.set_last_event("")
        self._refresh_counters()

    # -- setup ------------------------------------------------------------

    @staticmethod
    def _conveyor_config() -> ConveyorConfig:
        return ConveyorConfig(seed=int(_setting("seed", 42)),
                              max_products=int(_setting("maxProducts", 30)))

    def _destroy_frame_provider(self):
        if self._frames is not None:
            self._frames.destroy()
            self._frames = None

    async def _create_frame_provider_async(self, main):
        """Create the inspection viewport (needs a renderer; skipped in headless tests).

        Waits until the main viewport has rendered the new scene first: every D3D crash seen
        on 2026-10-21 happened when the 2nd viewport was created while RTX was still
        initialising (renderer.asyncInit) or uploading a new stage.
        """
        if main is None:
            return
        from omni.kit.viewport.utility import next_viewport_frame_async

        from .frame_provider import InspectionFrameProvider

        self._ui.set_status("waiting for renderer...")
        await next_viewport_frame_async(main, 60)
        self._ui.set_status("starting inspection camera...")
        self._frames = InspectionFrameProvider(L.CAMERA_PATH, L.CAMERA_RESOLUTION)
        await self._frames.ready_async()

    async def _setup_inspection_async(self):
        """Create the inspector for the inspection viewport."""
        if self._frames is None:
            carb.log_warn(f"{LOG_PREFIX} no viewport: vision inspection disabled")
            return

        cfg_path = _resolve(_setting("inspectorConfig", ""))
        cfg = InspectorConfig.load(cfg_path) if os.path.isfile(cfg_path) else InspectorConfig()
        if cfg.roi is None:
            cfg.roi = inspection_roi(L.CAMERA_RESOLUTION, L.CAMERA_FOCAL_MM, L.CAMERA_H_APERTURE_MM,
                                     L.CAMERA_HEIGHT_ABOVE_BELT, L.CONVEYOR_WIDTH / 2.0 - 0.02,
                                     L.INSPECTION_HALF_LENGTH)
        self._inspector = VisionInspector(cfg)
        print(f"{LOG_PREFIX} inspector ready: {cfg} (config file: {cfg_path or 'none'})")

    def _open_run(self):
        seed = self._sim.config.seed
        run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_seed{seed}"
        self.run_dir = os.path.join(_resolve(_setting("outputDir", "${data}/visiontwin_results")), "runs", run_id)
        self._log = InspectionLog(self.run_dir, record_frames=bool(_setting("recordFrames", True)))
        meta = {"run_id": run_id, "seed": seed, "max_products": self._sim.config.max_products,
                "lighting_condition": "default", "camera_resolution": list(L.CAMERA_RESOLUTION),
                "inspector": self._inspector.config.__dict__}
        with open(os.path.join(self.run_dir, "run.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        self._run_id = run_id
        print(f"{LOG_PREFIX} run {run_id} -> {self.run_dir}")

    # -- simulation tick --------------------------------------------------

    def _unsubscribe(self):
        if self._update_sub is not None:
            self._update_sub.reset()
            self._update_sub = None

    def _on_update(self, event):
        dt = float(event["dt"])
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return
        inspected = []
        for e in self._sim.step(dt):
            p = self._sim.tracker.get(e.product_id)
            if e.kind == SPAWN:
                scene.spawn_product_prim(stage, p.product_id, p.defect_kind, p.x)
            elif e.kind == INSPECT:
                inspected.append(p.product_id)
            elif e.kind == REJECT:
                scene.move_product_to_reject_bin(stage, p.product_id)
            elif e.kind == EXIT and p.exit_route == "pass":
                scene.remove_product_prim(stage, p.product_id)
            msg = f"t={e.time:7.3f}s id={e.product_id:04d} {e.kind}"
            print(f"{LOG_PREFIX} {msg}")
            self._ui.set_last_event(msg)
        for p in self._sim.tracker.on_belt():
            scene.move_product_prim(stage, p.product_id, p.x)
        # Request frames after the prims moved, so the next render shows the product on the line.
        for pid in inspected:
            self._request_inspection(pid)
        self._refresh_counters()
        if self._sim.finished:
            self.stop()
            self._ui.set_status("finished")

    # -- inspection -------------------------------------------------------

    def _request_inspection(self, product_id: int):
        if self._frames is None or self._inspector is None:
            return
        sim_time = self._sim.time
        speed = self._sim.config.speed
        self._frames.request_frame(
            lambda rgb, cap_ms, stale: self._on_frame(product_id, rgb, cap_ms, stale, sim_time, speed))

    def _on_frame(self, product_id, rgb, capture_ms, stale, sim_time, speed):
        result = self._inspector.inspect(rgb)  # pixels only
        if stale:
            # Same pixels as the previous capture: this frame may show another product.
            # Never guess; Day 4 treats unknown as a separate (safe) route.
            result.label, result.reason = UNKNOWN, "stale frame (identical to previous capture)"
            carb.log_warn(f"{LOG_PREFIX} id={product_id:04d} stale frame -> unknown")
        p = self._sim.tracker.get(product_id)
        p.prediction = result.label
        frame_file = self._log.save_frame(product_id, rgb) if self._log else None
        if self._log:
            self._log.append(InspectionRecord(
                run_id=self._run_id, seed=self._sim.config.seed, product_id=product_id,
                ground_truth=p.ground_truth,  # evaluation only, copied from the tracker
                predicted_label=result.label, score=round(result.score, 4),
                mean_hue=round(result.mean_hue, 2), area_px=result.area_px,
                capture_latency_ms=round(capture_ms, 2),
                inspection_latency_ms=round(result.latency_ms, 3),
                simulation_time_s=round(sim_time, 3), conveyor_speed=speed,
                lighting_condition="default", frame_file=frame_file or "", reason=result.reason))
        msg = f"id={product_id:04d} vision={result.label} score={result.score:.2f} ({result.latency_ms:.1f} ms)"
        print(f"{LOG_PREFIX} {msg}")
        self._ui.set_last_event(msg)
        self._refresh_counters()

    def _refresh_counters(self):
        products = self._sim.tracker.all()
        n_exit = sum(p.state == ProductState.EXITED for p in products)
        n_rej = sum(p.exit_route == "reject" for p in products)
        n_insp = sum(p.inspected_time is not None for p in products)
        n_pred = {k: sum(p.prediction == k for p in products) for k in ("good", "defect", "unknown")}
        self._ui.set_counters(
            f"t={self._sim.time:.1f}s  spawned={len(products)}  inspected={n_insp}  "
            f"exited={n_exit}  rejected={n_rej}  on_belt={len(self._sim.tracker.on_belt())}\n"
            f"vision: good={n_pred['good']} defect={n_pred['defect']} unknown={n_pred['unknown']}"
        )
