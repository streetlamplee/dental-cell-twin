"""VisionTwin factory extension: wires the conveyor simulation to the USD stage, the
inspection camera, the reject-line sorting and the UI."""

import asyncio
import json
import math
import os
import time

import carb
import carb.eventdispatcher
import numpy as np
import carb.settings
import carb.tokens
import omni.ext
import omni.kit.app
import omni.usd
from omni.kit.viewport.utility import get_active_viewport

from . import scene_manager as scene
from .core import layout as L
from .core.camera_model import inspection_roi
from .core.conveyor import (EXIT, INSPECT, LOAD, REJECT, SORT, SPAWN, STATION, UNLOAD, ConveyorConfig,
                            ConveyorSim, ProcessStation)
from .core.event_log import EventLog
from .core.inspection_log import InspectionLog, InspectionRecord
from .core.product_tracker import ProductState
from .core.run_results import build_rows, write_csv
from .core.product_catalog import BOX, ProductCatalog
from .core.sorting import SortingController
from .core.vision_inspector import UNKNOWN, InspectorConfig, VisionInspector
from .dashboard import Dashboard

LOG_PREFIX = "[visiontwin.factory]"
SETTINGS = "/exts/visiontwin.factory"
# Lighting conditions for experiments: light intensity factor applied to the key + dome lights.
LIGHT_FACTORS = {"default": 1.0, "dark": 0.35, "bright": 2.0}


def _lighting() -> str:
    name = str(_setting("lighting", "default"))
    return name if name in LIGHT_FACTORS else "default"

_instance = None


def get_instance():
    """The running extension, for automation scripts (e.g. scripts/collect_frames.py)."""
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
        self._catalog = self._make_catalog()
        self._sim = ConveyorSim(self._conveyor_config())
        self._new_sorter()
        self._update_sub = None
        self._scene_ready = False
        self._frames = None  # InspectionFrameProvider, only when a viewport exists
        self._main_viewport = None
        self._inspector = None
        self._log = None  # InspectionLog for the current run
        self._events = None  # EventLog (events.csv) for the current run
        self._anims = {}  # product_id -> sim time the reject animation started
        self._mill = None  # MillStation (CAD asset), when the asset files exist
        self.run_dir = None
        self.run_complete = False
        self.summary = None
        self._ui = Dashboard(
            on_build=self._on_build,
            on_start=self.start,
            on_stop=self.stop,
            on_reset=self.reset,
            on_speed=self._sim.set_speed,
            initial_speed=self._sim.config.speed,
            on_setting=self._set_setting,
            initial={k: _setting(k, d) for k, d in (("part", BOX), ("seed", 42), ("maxProducts", 30),
                                                    ("defectRate", 0.3))},
            on_view=self.set_view,
        )

    # -- dashboard callbacks ------------------------------------------------

    @staticmethod
    def _set_setting(name: str, value) -> None:
        """Line setup from the dashboard; takes effect on Build Scene / Reset."""
        carb.settings.get_settings().set(f"{SETTINGS}/{name}", value)

    def set_view(self, index: int) -> None:
        """Main viewport camera: 0 overview, 1 mill close-up, 2 inspection camera."""
        cams = (L.OVERVIEW_CAMERA_PATH, L.MILL_CAMERA_PATH, L.CAMERA_PATH)
        main = self.main_viewport
        if main is not None and 0 <= index < len(cams):
            main.camera_path = cams[index]

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

    @property
    def main_viewport(self):
        """The main (overview) viewport. Remembered before the inspection window exists,
        because get_active_viewport() may return the inspection window afterwards."""
        if self._main_viewport is None:
            self._main_viewport = get_active_viewport()
        return self._main_viewport

    def _on_build(self):
        asyncio.ensure_future(self.build_scene_async())

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
        self._catalog = self._make_catalog()
        scene.build_factory_scene(ctx.get_stage(), *self._camera_params(), light_factor=LIGHT_FACTORS[_lighting()])
        self._mill = self._create_mill_station(ctx.get_stage())
        self._reset_run_state()
        await omni.kit.app.get_app().next_update_async()
        self._use_stage_lights()
        if main is not None:
            main.camera_path = L.OVERVIEW_CAMERA_PATH  # deterministic framing
            # Render load: the main view is for people, the inspection viewport (fixed 640x480)
            # is what the vision uses; rendering the main view at a lower scale saves GPU time.
            main.resolution_scale = float(_setting("mainViewportScale", 0.5))
        await self._create_frame_provider_async(main)
        await self._setup_inspection_async()
        self._scene_ready = True
        self._ui.set_status("scene ready")
        self._refresh_counters()
        print(f"{LOG_PREFIX} factory scene built")

    @staticmethod
    def _use_stage_lights():
        """Light the scene with our stage lights only. The viewport's auto light rig
        ("Default": dome exposure 9 + distant exposure 10) is applied to new stages and
        outshines KeyLight/Ambient, so lighting conditions had almost no effect (2026-10-22)."""
        try:
            import omni.kit.actions.core

            omni.kit.actions.core.execute_action("omni.kit.viewport.menubar.lighting", "set_lighting_mode_stage")
        except Exception as exc:  # the lighting menu extension is optional
            carb.log_warn(f"{LOG_PREFIX} could not switch to stage lights: {exc}")

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
        self._reset_run_state()
        stage = omni.usd.get_context().get_stage()
        if self._scene_ready and stage:
            scene.clear_products(stage)
            scene.set_pusher(stage, scene.PUSHER_HOME_Y)
        self._ui.set_status("reset")
        self._ui.set_last_event("")
        self._refresh_counters()

    # -- setup ------------------------------------------------------------

    @staticmethod
    def _make_catalog() -> ProductCatalog:
        part = str(_setting("part", BOX))
        return ProductCatalog(part, _resolve(_setting("partsDir", "")) if part != BOX else None)

    @property
    def _rest_dz(self) -> float:
        return scene.BOX_REST_DZ if self._catalog.is_box else scene.PART_REST_DZ

    def _camera_params(self):
        """(height above belt, focal mm) of the inspection camera for the current product."""
        cam = self._catalog.camera
        return (cam.height_above_belt, cam.focal_mm) if cam else (L.CAMERA_HEIGHT_ABOVE_BELT, L.CAMERA_FOCAL_MM)

    def _conveyor_config(self) -> ConveyorConfig:
        process = self._catalog.process
        if process:  # dental line: the mill is a processing station on the line
            name, cycle = process
            cycle = float(_setting("cycleS", cycle))  # experiment override
            extra = dict(process=ProcessStation(name, L.MILL_ENTRY_X, L.MILL_EXIT_X, cycle),
                         spawn_interval=self._catalog.spawn_interval or ConveyorConfig.spawn_interval)
        else:  # the mill only plays a visual cycle when a product passes
            extra = dict(stations=(("mill", L.MILL_X),))
        if _setting("spawnInterval", None) is not None:  # experiment override
            extra["spawn_interval"] = float(_setting("spawnInterval", None))
        return ConveyorConfig(seed=int(_setting("seed", 42)),
                              max_products=int(_setting("maxProducts", 30)),
                              defect_rate=float(_setting("defectRate", 0.3)),
                              defect_kinds=self._catalog.defect_kinds,
                              speed=float(_setting("speed", 0.5)), **extra)

    def _new_sorter(self):
        self._sorter = SortingController(unknown_policy=str(_setting("unknownPolicy", "reject")))
        self._sim.reject_decider = self._sorter.decide

    def _reset_run_state(self):
        self._catalog = self._make_catalog()
        self._sim.config = self._conveyor_config()
        self._sim.reset()
        self._new_sorter()
        self._log = None
        if getattr(self, "_events", None) is not None:
            self._events.close()
        self._events = None
        self._anims.clear()
        self._frame_mismatches = 0
        self._stale_frames = 0
        self.run_complete = False
        self.summary = None

    def _create_mill_station(self, stage):
        """Reference the CAD-converted mill (Day 5). Optional: skipped if the files are missing."""
        asset = _resolve(_setting("millAsset", ""))
        kin = _resolve(_setting("millKinematics", ""))
        if not (_setting("millStation", True) and os.path.isfile(asset) and os.path.isfile(kin)):
            carb.log_warn(f"{LOG_PREFIX} mill station skipped (asset={asset!r}, kinematics={kin!r})")
            return None
        from .mill_station import MillStation

        try:
            process = self._catalog.process
            machining = (float(_setting("cycleS", process[1])) * (1.0 - L.MILL_LOAD_FRACTION - L.MILL_UNLOAD_FRACTION)
                         if process else 3.0)
            station = MillStation(stage, asset, kin, hide_work=process is not None, cycle_duration=machining)
        except Exception as exc:  # the line must still work without the visual station
            carb.log_error(f"{LOG_PREFIX} mill station failed: {exc}")
            return None
        print(f"{LOG_PREFIX} mill station ready ({asset})")
        return station

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
        if not self._catalog.is_box:  # per-part calibration next to the box config
            cfg_path = os.path.join(os.path.dirname(cfg_path), f"inspector_{self._catalog.part}.json")
        cfg = InspectorConfig.load(cfg_path) if os.path.isfile(cfg_path) else InspectorConfig()
        if cfg.roi is None:
            height, focal = self._camera_params()
            cfg.roi = inspection_roi(L.CAMERA_RESOLUTION, focal, L.CAMERA_H_APERTURE_MM, height,
                                     L.CONVEYOR_WIDTH / 2.0 - 0.02, L.INSPECTION_HALF_LENGTH)
        self._inspector = VisionInspector(cfg)
        print(f"{LOG_PREFIX} inspector ready: {cfg} (config file: {cfg_path or 'none'})")

    def _open_run(self):
        seed = self._sim.config.seed
        run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_seed{seed}"
        self.run_dir = os.path.join(_resolve(_setting("outputDir", "${data}/visiontwin_results")), "runs", run_id)
        self._log = InspectionLog(self.run_dir, record_frames=bool(_setting("recordFrames", True)))
        self._events = EventLog(self.run_dir)
        meta = {"run_id": run_id, "seed": seed, "max_products": self._sim.config.max_products,
                "conveyor_speed": self._sim.config.speed, "spawn_interval": self._sim.config.spawn_interval,
                "defect_rate": self._sim.config.defect_rate, "unknown_policy": self._sorter.unknown_policy,
                "fixed_dt": float(_setting("fixedDt", 1.0 / 60.0)),
                "experiment": str(_setting("experiment", "")), "condition": str(_setting("condition", "")),
                "process_cycle_s": self._sim.config.process.cycle_s if self._sim.config.process else None,
                "part": self._catalog.part, "lighting_condition": _lighting(), "camera_resolution": list(L.CAMERA_RESOLUTION),
                "inspector": self._inspector.config.__dict__}
        with open(os.path.join(self.run_dir, "run.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        self._run_id = run_id
        self._run_t0 = time.perf_counter()
        print(f"{LOG_PREFIX} run {run_id} -> {self.run_dir}")

    def _run_ms(self) -> float:
        return (time.perf_counter() - self._run_t0) * 1000.0

    # -- simulation tick --------------------------------------------------

    def _unsubscribe(self):
        if self._update_sub is not None:
            self._update_sub.reset()
            self._update_sub = None

    def _on_update(self, event):
        # Fixed simulation step per update (default 1/60 s): the line advances by the same
        # amount every rendered frame, so runs are reproducible and the inspection deadline
        # does not shrink when rendering is slow (synchronous rendering ran at ~10 fps and
        # wall-clock dt made 5/30 verdicts late at 1.5 m/s). fixedDt=0 -> wall-clock dt.
        fixed_dt = float(_setting("fixedDt", 1.0 / 60.0))
        dt = fixed_dt if fixed_dt > 0 else float(event["dt"])
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            return
        inspected = []
        for e in self._sim.step(dt):
            p = self._sim.tracker.get(e.product_id)
            if e.kind == SPAWN:
                scene.spawn_product_prim(stage, p.product_id, p.defect_kind, p.x,
                                         self._catalog.variant_path(p.ground_truth, p.defect_kind),
                                         self._catalog.raw_path(p.ground_truth, p.defect_kind))
            elif e.kind == LOAD and self._mill is not None:
                # machining motion starts after the load transfer
                self._mill.cycle.trigger(e.time + L.MILL_LOAD_FRACTION * self._sim.config.process.cycle_s)
            elif e.kind == UNLOAD:
                scene.show_final_shape(stage, p.product_id)
                scene.set_product_pose(stage, p.product_id, self._belt_pose(p.x))
            elif e.kind == INSPECT:
                inspected.append(p.product_id)
            elif e.kind == REJECT:
                self._anims[p.product_id] = e.time
            elif e.kind == EXIT and p.exit_route == "pass":
                scene.remove_product_prim(stage, p.product_id)
            elif e.kind == STATION and e.station == "mill" and self._mill is not None:
                self._mill.cycle.trigger(e.time)
            reason = ""
            if e.kind in (REJECT, SORT):
                reason = f" ({self._sorter.decisions[p.product_id].reason})"
            msg = f"t={e.time:7.3f}s id={e.product_id:04d} {e.kind}{reason}"
            print(f"{LOG_PREFIX} {msg}")
            self._ui.set_last_event(msg)
            if self._events is not None:
                self._events.write(e.time, e.product_id, e.kind, e.x, e.station, reason.strip(" ()"))
        for p in self._sim.tracker.on_belt():
            scene.move_product_prim(stage, p.product_id, p.x, rest_dz=self._rest_dz)
        self._animate_rejects(stage, finish=False)
        if self._mill is not None:
            self._mill.apply(self._sim.time)
            self._animate_processing(stage)
        # Request frames after the prims moved, so the next render shows the product on the line.
        for pid in inspected:
            self._request_inspection(pid)
        self._refresh_counters()
        if self._sim.finished:
            self._animate_rejects(stage, finish=True)
            self.stop()
            self._ui.set_status("finished - writing results")
            asyncio.ensure_future(self._finalize_run_async())

    @staticmethod
    def _belt_pose(x: float) -> np.ndarray:
        m = np.eye(4)
        m[:3, 3] = (x, 0.0, L.CONVEYOR_TOP_Z + scene.PART_REST_DZ)
        return m

    def _animate_processing(self, stage):
        """Visual load -> machining -> unload of the product inside the mill station.
        load: belt entry -> platter (lifted arc); machining: rides the platter (B/C rotation),
        blank turns into the final shape half-way; unload: platter -> belt exit."""
        pid = self._sim.station_product
        st = self._sim.config.process
        if pid is None or st is None:
            return
        p = self._sim.tracker.get(pid)
        u = (self._sim.time - p.load_time) / st.cycle_s
        platter = self._mill.platter_pose()
        lf, uf = L.MILL_LOAD_FRACTION, L.MILL_UNLOAD_FRACTION
        if u < lf:
            pose = self._lift_lerp(self._belt_pose(st.x_entry), platter, u / lf)
        elif u < 1.0 - uf:
            pose = platter
            if u >= 0.5:
                scene.show_final_shape(stage, pid)
        else:  # unloading (or waiting for a blocked exit at the end of the transfer)
            scene.show_final_shape(stage, pid)
            pose = self._lift_lerp(platter, self._belt_pose(st.x_exit), min((u - (1.0 - uf)) / uf, 1.0))
        scene.set_product_pose(stage, pid, pose)

    @staticmethod
    def _lift_lerp(a: np.ndarray, b: np.ndarray, k: float, lift: float = 0.12) -> np.ndarray:
        """Translation lerp with a parabolic lift (transfer arm); rotation from the platter end."""
        k = min(max(k, 0.0), 1.0)
        m = (b if k > 0.5 else a).copy()
        m[:3, 3] = a[:3, 3] + (b[:3, 3] - a[:3, 3]) * k
        m[2, 3] += lift * 4 * k * (1 - k)
        return m

    def _animate_rejects(self, stage, finish: bool):
        for pid, t0 in list(self._anims.items()):
            u = 1.0 if finish else (self._sim.time - t0) / scene.REJECT_ANIM_S
            (x, y, z), pusher_y = scene.reject_motion(u, self._rest_dz)
            scene.move_product_prim(stage, pid, x, y, z)
            scene.set_pusher(stage, pusher_y)
            if u >= 1.0:
                del self._anims[pid]

    # -- inspection -------------------------------------------------------

    def _request_inspection(self, product_id: int):
        if self._frames is None or self._inspector is None:
            return
        p = self._sim.tracker.get(product_id)
        if self._log:
            p.inspection_start_ms = self._run_ms()
        sim_time = self._sim.time
        speed = self._sim.config.speed
        self._frames.request_frame(
            lambda rgb, cap_ms, stale, offset: self._on_frame(product_id, rgb, cap_ms, stale, offset,
                                                             sim_time, speed),
            on_error=lambda msg: self._on_frame_error(product_id, msg, sim_time))

    def _on_frame_error(self, product_id: int, message: str, sim_time: float = 0.0):
        """No usable frame: the product gets 'unknown' (never another product's verdict)."""
        carb.log_warn(f"{LOG_PREFIX} id={product_id:04d} capture failed ({message}) -> unknown")
        if self._events is not None:
            self._events.write(sim_time, product_id, "VISION", detail=f"unknown capture failed: {message}")
        p = self._sim.tracker.get(product_id)
        if self._log:
            p.inspection_end_ms = self._run_ms()
        if self._sorter.is_sorted(product_id):
            p.late_prediction = UNKNOWN
            self._sorter.record_late(product_id)
        else:
            p.prediction = UNKNOWN
        self._refresh_counters()

    def _on_frame(self, product_id, rgb, capture_ms, stale, frame_offset, sim_time, speed):
        result = self._inspector.inspect(rgb)  # pixels only
        if frame_offset != 0:
            # The image is not the stage state of the trigger update (frame targeting missed),
            # so it may show the product elsewhere or another product: never attach it.
            self._frame_mismatches += 1
            result.label, result.reason = UNKNOWN, f"frame mismatch (captured {frame_offset:+} frames)" \
                if frame_offset is not None else "frame mismatch (no frame number)"
            carb.log_warn(f"{LOG_PREFIX} id={product_id:04d} {result.reason} -> unknown")
        elif stale:
            # Same pixels as the previous capture. With a verified frame number (offset 0) this is
            # legitimate: identical parts at the same spot with periodic spacing render identically
            # (false "stale" on 2026-10-22, products 30/31). Only an unverifiable frame is unknown.
            self._stale_frames += 1
            if frame_offset is None:
                result.label, result.reason = UNKNOWN, "stale frame (identical to previous capture)"
                carb.log_warn(f"{LOG_PREFIX} id={product_id:04d} stale frame -> unknown")

        p = self._sim.tracker.get(product_id)
        if self._log:
            p.inspection_end_ms = self._run_ms()
        if self._sorter.is_sorted(product_id):
            p.late_prediction = result.label  # too late: recorded, never applied
            self._sorter.record_late(product_id)
            carb.log_warn(f"{LOG_PREFIX} id={product_id:04d} verdict arrived after sorting (late)")
        else:
            p.prediction, p.score = result.label, result.score
            p.defect_reason = result.defect_reason if result.label == "defect" else None

        frame_file = self._log.save_frame(product_id, rgb) if self._log else None
        if self._log:
            self._log.append(InspectionRecord(
                run_id=self._run_id, seed=self._sim.config.seed, product_id=product_id,
                ground_truth=p.ground_truth,  # evaluation only, copied from the tracker
                predicted_label=result.label, defect_reason=result.defect_reason,
                score=round(result.score, 4), mean_hue=round(result.mean_hue, 2), area_px=result.area_px,
                interior_ratio="" if math.isnan(result.interior_ratio) else round(result.interior_ratio, 4),
                interior_bright="" if math.isnan(result.interior_bright) else round(result.interior_bright, 4),
                capture_latency_ms=round(capture_ms, 2), frame_offset="" if frame_offset is None else frame_offset,
                inspection_latency_ms=round(result.latency_ms, 3),
                simulation_time_s=round(sim_time, 3), conveyor_speed=speed,
                lighting_condition=_lighting(), frame_file=frame_file or "", reason=result.reason))
        msg = f"id={product_id:04d} vision={result.label} score={result.score:.2f} ({result.latency_ms:.1f} ms)"
        print(f"{LOG_PREFIX} {msg}")
        self._ui.set_last_event(msg)
        if self._events is not None:
            self._events.write(sim_time, product_id, "VISION", detail=f"{result.label} {result.defect_reason}".strip())
        self._refresh_counters()

    # -- run results ------------------------------------------------------

    async def _finalize_run_async(self):
        """Write results.csv + summary.json once every pending frame has been handled."""
        app = omni.kit.app.get_app()
        for _ in range(600):
            if self.pending_frames == 0:
                break
            await app.next_update_async()
        if self._log is None:
            self.run_complete = True
            self._ui.set_status("finished (no inspection)")
            return
        products = self._sim.tracker.all()
        rows = build_rows(self._run_id, self._sim.config.seed, _lighting(), products, self._sorter.decisions)
        write_csv(os.path.join(self.run_dir, "results.csv"), rows)
        if self._events is not None:
            self._events.close()
        sorted_rows = [r for r in rows if r["sort_result"]]
        self.summary = {
            "run_id": self._run_id,
            "products": len(products),
            "sorted": len(sorted_rows),
            "sort_correct": sum(r["sort_correct"] is True for r in sorted_rows),
            "rejected": sum(r["sort_result"] == "reject" for r in sorted_rows),
            "fail_safe_rejects": sum("fail-safe" in r["sort_reason"] for r in sorted_rows),
            "late_results": len(self._sorter.late_results),
            "frame_mismatches": self._frame_mismatches,
            "stale_frames": self._stale_frames,
            "frame_target_misses": self._frames.frame_target_misses if self._frames else None,
            "capture_timeouts": self._frames.timeouts if self._frames else None,
            "not_exited": sum(p.state != ProductState.EXITED for p in products),
            "pending_frames_at_finalize": self.pending_frames,
            "simulation_time_s": round(self._sim.time, 3),
            "part": self._catalog.part,
            "throughput_per_hour": round(len(sorted_rows) / self._sim.time * 3600.0, 1) if self._sim.time else None,
        }
        if self._sim.config.process is not None:  # dental milling line metrics
            st = self._sim.config.process
            self.summary["line"] = {
                "station": st.name, "cycle_s_compressed": st.cycle_s,
                "spawn_interval_s": self._sim.config.spawn_interval,
                "station_utilization": round(self._sim.station_utilization, 4),
                "station_busy_s": round(self._sim.station_busy_time, 3),
                "station_exit_blocked_s": round(self._sim.station_blocked_time, 3),
                "queue_max": self._sim.queue_max,
                "queue_mean": round(self._sim.queue_mean, 3),
            }
        with open(os.path.join(self.run_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(self.summary, f, indent=2)
        self.run_complete = True
        self._ui.set_status(f"finished: sorted {self.summary['sort_correct']}/{self.summary['sorted']} correct")
        print(f"{LOG_PREFIX} summary {json.dumps(self.summary)}")

    def _refresh_counters(self):
        products = self._sim.tracker.all()
        n_insp = sum(p.inspected_time is not None for p in products)
        n_pred = {k: sum(p.prediction == k for p in products) for k in ("good", "defect", "unknown")}
        d = self._sorter.decisions.values()
        n_pass = sum(x.route == "pass" for x in d)
        n_rej = sum(x.route == "reject" for x in d)
        n_ok = sum(SortingController.route_correct(self._sim.tracker.get(x.product_id).ground_truth, x.route)
                   for x in d)
        self._ui.set_counters(
            f"t={self._sim.time:.1f}s  spawned={len(products)}  inspected={n_insp}  "
            f"on_belt={len(self._sim.tracker.on_belt())}\n"
            f"vision: good={n_pred['good']} defect={n_pred['defect']} unknown={n_pred['unknown']}\n"
            f"sorted: pass={n_pass} reject={n_rej} correct={n_ok}/{len(d)}  "
            f"late={len(self._sorter.late_results)} frame_err={getattr(self, '_frame_mismatches', 0)}"
            + (f"\nmill: {'MACHINING id=%04d' % self._sim.station_product if self._sim.station_product else 'idle'}"
               f"  queue={self._sim.queue_len} (max {self._sim.queue_max})"
               f"  util={self._sim.station_utilization * 100:.0f}%"
               if self._sim.config.process is not None else "")
        )
