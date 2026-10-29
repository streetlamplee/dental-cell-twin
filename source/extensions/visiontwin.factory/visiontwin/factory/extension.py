"""VisionTwin factory extension: wires the conveyor simulation to the USD stage, the
inspection camera, the reject-line sorting and the UI.

Two line layouts:
  belt  box / KFL08: one conveyor, fixed top-down camera over the inspection line
  cell  dental crown: conveyor -> inline inspection cell (5-axis machine with the camera on
        its spindle; several views per product) -> conveyor -> reject line
"""

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
import omni.kit.pipapi
import omni.usd
from omni.kit.viewport.utility import get_active_viewport

from . import scene_manager as scene
from .core import layout as L
from .core.camera_model import inspection_roi
from .core.conveyor import (EXIT, INSPECT, REJECT, SORT, SPAWN, UNLOAD, VIEW, ConveyorConfig, ConveyorSim,
                            ProcessStation)
from .core.event_log import EventLog
from .core.inspection_log import InspectionLog, InspectionRecord
from .core.product_tracker import ProductState
from .core.run_results import build_rows, write_csv
from .core.product_catalog import BOX, ProductCatalog
from .core.sorting import SortingController
from .core.vision_inspector import (UNKNOWN, InspectionResult, InspectorConfig, VisionInspector, combine_views,
                                    load_view_configs)
from .dashboard import Dashboard
from .runtime_session import RuntimeSession

LOG_PREFIX = "[visiontwin.factory]"
SETTINGS = "/exts/visiontwin.factory"
# Lighting conditions for experiments: light intensity factor applied to the key + dome lights.
LIGHT_FACTORS = {"default": 1.0, "dark": 0.35, "bright": 2.0}


def _vision_on() -> bool:
    """Vision inspection on/off (setting `vision`, applied on Build Scene / Reset). Off: no
    inspection camera, no verdicts, every product passes the reject line; the machine, robot
    and line run as usual. The app's GUI default is off (2026-10-24); scripts that measure
    vision pass vision=true."""
    return bool(_setting("vision", True))


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
        carb.log_info(f"{LOG_PREFIX} startup")
        self._catalog = self._make_catalog()
        self._sim = ConveyorSim(self._conveyor_config())
        self._new_sorter()
        self._update_sub = None
        self._scene_ready = False
        self._built_part = None  # product the current scene was built for
        self._vision_setup_pending = False  # inspection camera being created by Start
        self._frames = None  # InspectionFrameProvider, only when a viewport exists
        self._main_viewport = None
        self._inspector = None
        self._log = None  # InspectionLog for the current run
        self._events = None  # EventLog (events.csv) for the current run
        self._anims = {}  # product_id -> sim time the reject animation started
        self._cell = None  # InspectionCell (CAD machine + spindle camera), dental crown line
        self._arm = None  # RobotArm (Seeed reBot Arm) moving products in/out of the cell
        self._cell_cycle_cache = None  # (part, CellCycle)
        self._inspectors = []  # cell: one VisionInspector per view
        self._model = None  # cell: learned ModelInspector (ONNX), runs next to the rule inspectors
        self._view_results = {}  # cell: product_id -> {view index: InspectionResult}
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
                                                    ("defectRate", 0.3), ("vision", True))},
            on_view=self.set_view,
            on_teach=self.open_teach_pendant,
        )
        self._runtime = RuntimeSession(self)
        _instance = self  # publish only after the extension is fully initialized

    # -- dashboard callbacks ------------------------------------------------

    @staticmethod
    def _set_setting(name: str, value) -> None:
        """Line setup from the dashboard; takes effect on Build Scene / Reset."""
        carb.settings.get_settings().set(f"{SETTINGS}/{name}", value)

    def set_view(self, index: int) -> None:
        """Main viewport camera: 0 overview, 1 inspection cell close-up, 2 inspection camera."""
        cell = self._catalog.cell is not None
        cams = (L.OVERVIEW_CAMERA_PATH, L.CELL_OVERVIEW_CAMERA_PATH if cell else L.OVERVIEW_CAMERA_PATH,
                self._inspection_camera_path)
        main = self.main_viewport
        if main is not None and 0 <= index < len(cams):
            main.camera_path = cams[index]

    def open_teach_pendant(self):
        """Surface teaching on the cell's machine (Day 13): stops the line, shows the URDF tool
        and block, and opens the pendant. Closing it puts the cell back."""
        if not self._scene_ready or self._cell is None:
            self._ui.set_status("build the crown (inspection cell) scene first")
            return None
        if getattr(self, "_pendant", None) is not None:
            return self._pendant
        from .core.teach import Teacher
        from .core.urdf_model import load_urdf
        from .teach_pendant import TeachPendant

        self.stop()
        self._cell.teach_mode(True)
        main = self.main_viewport
        if main is not None:
            main.camera_path = L.TEACH_CAMERA_PATH
        teacher = Teacher.from_urdf(load_urdf(_resolve(_setting("millUrdf", ""))))
        out = os.path.join(_resolve(_setting("outputDir", "${data}/visiontwin_results")), "teach")

        def closed():
            self._pendant = None
            if self._cell is not None:
                self._cell.teach_mode(False)
                self._cell.apply(None)
            self._ui.set_status("teach pendant closed")

        self._pendant = TeachPendant(teacher, self._cell.set_joints, out, closed)
        self._ui.set_status("teaching (line stopped)")
        return self._pendant

    def on_shutdown(self):
        global _instance
        _instance = None
        carb.log_info(f"{LOG_PREFIX} shutdown")
        self._runtime.shutdown()
        self._close_teach_pendant()
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
        self._runtime.tasks.create(self.build_scene_async())

    async def _enable_vision_then_start(self):
        generation = self._runtime.generation
        try:
            await self._create_frame_provider_async(self.main_viewport)
            if not self._runtime.valid(generation):
                return
            await self._setup_inspection_async()
        finally:
            if self._runtime.valid(generation):
                self._vision_setup_pending = False
        if not self._runtime.valid(generation):
            return
        if self._frames is None:
            self._ui.set_status("no inspection camera: vision unavailable")
            return
        self.start()

    def _close_teach_pendant(self):
        pendant = getattr(self, "_pendant", None)
        if pendant is not None:
            pendant.destroy()

    async def build_scene_async(self):
        if self._runtime.building or not self._runtime.alive:
            return
        self._runtime.building = True
        try:
            await self._build_scene_async()
        finally:
            self._runtime.building = False

    async def _build_scene_async(self):
        self._runtime.invalidate("build")
        generation = self._runtime.generation
        self._scene_ready = False
        self._close_teach_pendant()
        self.stop()
        main = self.main_viewport
        # Order matters (2026-10-21):
        #  - creating the inspection viewport BEFORE new_stage left the main viewport
        #    rendering nothing, so it is (re)created after the scene exists;
        #  - creating it while RTX still initialises crashed D3D, so wait for main frames.
        self._destroy_frame_provider()
        self._ui.set_status("creating new stage...")
        ctx = omni.usd.get_context()
        self._runtime.changing_stage = True
        try:
            await ctx.new_stage_async()
        finally:
            self._runtime.changing_stage = False
        if not self._runtime.valid(generation):
            return
        self._catalog = self._make_catalog()
        layout = scene.CELL if self._catalog.cell else scene.BELT
        scene.build_factory_scene(ctx.get_stage(), *self._camera_params(), light_factor=LIGHT_FACTORS[_lighting()],
                                  layout=layout)
        self._cell = self._create_cell(ctx.get_stage()) if layout == scene.CELL else None
        self._arm = self._create_arm(ctx.get_stage()) if self._cell is not None else None
        self._reset_run_state()
        await omni.kit.app.get_app().next_update_async()
        if not self._runtime.valid(generation):
            return
        self._use_stage_lights()
        if main is not None:
            main.camera_path = L.OVERVIEW_CAMERA_PATH  # deterministic framing
            # Render load: the main view is for people, the inspection viewport (fixed 640x480)
            # is what the vision uses; rendering the main view at a lower scale saves GPU time.
            main.resolution_scale = float(_setting("mainViewportScale", 0.5))
        self._inspector, self._inspectors, self._model = None, [], None
        if _vision_on():
            await self._create_frame_provider_async(main)
            if not self._runtime.valid(generation):
                return
            await self._setup_inspection_async()
        if not self._runtime.valid(generation):
            return
        self._scene_ready = True
        self._built_part = self._catalog.part
        self._ui.set_status("scene ready")
        self._refresh_counters()
        print(f"{LOG_PREFIX} factory scene built (vision {'on' if _vision_on() else 'off'})")

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
        if self._catalog.part != self._built_part:  # Reset re-reads the product setting, the scene does not change
            self._ui.set_status(f"product changed to {self._catalog.part}: press Build Scene")
            return
        if _vision_on() and self._frames is None and self.main_viewport is not None:
            # Vision ticked after Build Scene (GUI check 2026-10-24: Reset + Start ran without
            # inspection and wrote no record): create the inspection camera first, then start.
            if not self._vision_setup_pending:
                self._vision_setup_pending = True
                self._runtime.tasks.create(self._enable_vision_then_start())
            return
        if self._log is None and self._sim.time == 0.0:
            self._new_sorter()  # vision may have been ticked after Reset: the sorter must match it
        if self._log is None and (self._inspector is not None or not _vision_on()):
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
        self._runtime.invalidate("reset")
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

    @property
    def _inspection_camera_path(self) -> str:
        return L.CELL_CAMERA_PATH if self._catalog.cell else L.CAMERA_PATH

    def _cell_cycle(self):
        """CellCycle of the current part (pure Python; needed before the scene exists)."""
        cached = getattr(self, "_cell_cycle_cache", None)  # also used from on_startup's first config
        if cached is None or cached[0] != self._catalog.part:
            from .inspection_cell import build_cycle

            self._cell_cycle_cache = (self._catalog.part,
                                      build_cycle(_resolve(_setting("millKinematics", "")), self._catalog.cell))
        return self._cell_cycle_cache[1]

    def _conveyor_config(self) -> ConveyorConfig:
        extra = {}
        if self._catalog.cell:  # dental crown line: the inspection cell is a station in the line
            cycle = self._cell_cycle()
            extra = dict(process=ProcessStation("cell", L.CELL_ENTRY_X, L.CELL_EXIT_X, cycle.cycle_s,
                                                tuple(cycle.view_times), inspects=True),
                         spawn_interval=self._catalog.spawn_interval or ConveyorConfig.spawn_interval)
        if _setting("spawnInterval", None) is not None:  # experiment override
            extra["spawn_interval"] = float(_setting("spawnInterval", None))
        return ConveyorConfig(seed=int(_setting("seed", 42)),
                              max_products=int(_setting("maxProducts", 30)),
                              defect_rate=float(_setting("defectRate", 0.3)),
                              defect_kinds=self._catalog.defect_kinds,
                              speed=float(_setting("speed", 0.5)), **extra)

    def _new_sorter(self):
        self._sorter = SortingController(unknown_policy=str(_setting("unknownPolicy", "reject")),
                                         inspection=_vision_on())
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
        self._view_results.clear()
        self._view_retakes = 0
        self._frame_mismatches = 0
        self._stale_frames = 0
        self.run_complete = False
        self.summary = None

    def _create_cell(self, stage):
        """Reference the CAD-converted machine as the inline inspection cell (Day 11)."""
        asset = _resolve(_setting("millAsset", ""))
        kin = _resolve(_setting("millKinematics", ""))
        if not (os.path.isfile(asset) and os.path.isfile(kin)):
            carb.log_error(f"{LOG_PREFIX} inspection cell missing (asset={asset!r}, kinematics={kin!r})")
            return None
        from .inspection_cell import InspectionCell

        cell = InspectionCell(stage, asset, kin, self._catalog.cell, self._cell_cycle())
        print(f"{LOG_PREFIX} inspection cell ready ({asset}, cycle {cell.cycle.cycle_s:.2f}s, "
              f"views {[v.name for v in cell.cycle.views]})")
        return cell

    def _create_arm(self, stage):
        """Transfer robot of the cell (Day 12). Optional: without the robot asset the product
        moves on a lifted arc with the same timing, so runs do not depend on it."""
        name = self._catalog.cell.transfer
        if not name:
            return None
        base = _resolve(_setting("robotsDir", ""))
        asset, kin = os.path.join(base, f"{name}.usd"), os.path.join(base, f"{name}.kinematics.json")
        if not (os.path.isfile(asset) and os.path.isfile(kin)):
            carb.log_warn(f"{LOG_PREFIX} transfer robot {name!r} missing ({asset}); products move on an arc. "
                          "Run scripts/fetch_robot.ps1 and scripts/urdf_mesh_to_usd.ps1 to add it.")
            return None
        from .robot_arm import RobotArm, build_transfer

        cycle = self._cell.cycle
        key = (self._catalog.part, asset)
        cached = getattr(self, "_transfer_cache", None)
        if cached is None or cached[0] != key:
            seat = self._cell.root @ cycle.product_seat(cycle.load_pose)
            transfer = build_transfer(kin, self._belt_pose(L.CELL_ENTRY_X), seat, self._belt_pose(L.CELL_EXIT_X),
                                      cycle.timing.load_s, cycle.timing.unload_s)
            self._transfer_cache = cached = (key, transfer)
        arm = RobotArm(stage, asset, cached[1])
        print(f"{LOG_PREFIX} transfer robot ready ({asset})")
        return arm

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

        generation = self._runtime.generation
        self._ui.set_status("waiting for renderer...")
        await next_viewport_frame_async(main, 60)
        if not self._runtime.valid(generation):
            return
        self._ui.set_status("starting inspection camera...")
        provider = InspectionFrameProvider(self._inspection_camera_path, L.CAMERA_RESOLUTION)
        self._frames = provider
        try:
            await provider.ready_async()
        except BaseException:
            if self._frames is provider:
                self._frames = None
            provider.destroy()
            raise
        if not self._runtime.valid(generation):
            if self._frames is provider:
                self._frames = None
            provider.destroy()

    async def _setup_inspection_async(self):
        """Create the inspector for the inspection viewport."""
        if self._frames is None:
            carb.log_warn(f"{LOG_PREFIX} no viewport: vision inspection disabled")
            return
        cfg_path = _resolve(_setting("inspectorConfig", ""))
        if not self._catalog.is_box:  # per-part calibration next to the box config
            cfg_path = os.path.join(os.path.dirname(cfg_path), f"inspector_{self._catalog.part}.json")
        if self._catalog.cell:
            self._setup_cell_inspectors(cfg_path)
            return
        self._inspectors = []
        cfg = InspectorConfig.load(cfg_path) if os.path.isfile(cfg_path) else InspectorConfig()
        if cfg.roi is None:
            height, focal = self._camera_params()
            cfg.roi = inspection_roi(L.CAMERA_RESOLUTION, focal, L.CAMERA_H_APERTURE_MM, height,
                                     L.CONVEYOR_WIDTH / 2.0 - 0.02, L.INSPECTION_HALF_LENGTH)
        self._inspector = VisionInspector(cfg)
        print(f"{LOG_PREFIX} inspector ready: {cfg} (config file: {cfg_path or 'none'})")

    def _setup_cell_inspectors(self, cfg_path: str):
        """One inspector per view (each view is calibrated on its own frames). Uncalibrated:
        permissive white-product defaults, so a calibration run can be recorded."""
        spec, cycle = self._catalog.cell, self._cell_cycle()
        n = len(cycle.views)
        cfgs = load_view_configs(cfg_path) if os.path.isfile(cfg_path) else []
        if len(cfgs) != n:
            if cfgs:
                carb.log_warn(f"{LOG_PREFIX} {cfg_path} has {len(cfgs)} views, the cell has {n}: recalibrate")
            cfgs = [InspectorConfig(segment="bright", color_metric="ab") for _ in range(n)]
        roi = inspection_roi(L.CAMERA_RESOLUTION, spec.focal_mm, L.CAMERA_H_APERTURE_MM, spec.standoff_m,
                             spec.roi_half_m, spec.roi_half_m)
        for c in cfgs:
            c.roi = c.roi or roi
        self._inspectors = [VisionInspector(c) for c in cfgs]
        self._inspector = self._inspectors[0]
        print(f"{LOG_PREFIX} cell inspectors ready: {n} views, roi {roi} (config file: {cfg_path})")
        self._model = self._load_model([v.name for v in cycle.views], roi)

    def _load_model(self, views, roi):
        """Learned inspector (Day 12) from inspectorModel (ONNX + model card), or None.
        ONNX Runtime is installed into Kit's Python on first use (omni.kit.pipapi, with its
        dependencies; the extension's own pip list uses --no-deps)."""
        path = _resolve(_setting("inspectorModel", "")) if _setting("inspectorModel", "") else ""
        if not path or not os.path.isfile(path):
            return None
        from .core.model_inspector import ModelCard, ModelInspector

        card = ModelCard.load(os.path.splitext(path)[0] + ".json")
        if card.views != list(views) or tuple(card.roi) != tuple(roi):
            carb.log_error(f"{LOG_PREFIX} model {path} was trained for views {card.views} / roi {card.roi}, "
                           f"the cell has {views} / {roi}: model disabled")
            return None
        omni.kit.pipapi.install("onnxruntime-directml", module="onnxruntime")
        import onnxruntime as ort

        sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])

        def network(batch):
            logit, view_logits = sess.run(None, {"views": batch.astype(np.float32)})
            return float(np.ravel(logit)[0]), list(np.ravel(view_logits))

        print(f"{LOG_PREFIX} learned inspector ready: {path} (decision: {_setting('decision', 'rules')})")
        return ModelInspector(network, card)

    def _open_run(self):
        seed = self._sim.config.seed
        run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns() % 1_000_000_000:09d}_seed{seed}"
        self.run_dir = os.path.join(_resolve(_setting("outputDir", "${data}/visiontwin_results")), "runs", run_id)
        self._log = InspectionLog(self.run_dir, record_frames=bool(_setting("recordFrames", True)))
        self._events = EventLog(self.run_dir)
        meta = {"run_id": run_id, "seed": seed, "max_products": self._sim.config.max_products,
                "conveyor_speed": self._sim.config.speed, "spawn_interval": self._sim.config.spawn_interval,
                "defect_rate": self._sim.config.defect_rate, "unknown_policy": self._sorter.unknown_policy,
                "fixed_dt": float(_setting("fixedDt", 1.0 / 60.0)),
                "generation": self._runtime.generation,
                "capture_wall_timeout_s": float(_setting("captureWallTimeoutS", 30.0)),
                "capture_update_budget": int(_setting("captureUpdateBudget", 180)),
                "capture_delivery_delay_s": float(_setting("captureDeliveryDelayS", 0.0)),
                "main_viewport_scale": float(_setting("mainViewportScale", 0.5)),
                "async_rendering": carb.settings.get_settings().get("/app/asyncRendering"),
                "kit_version": omni.kit.app.get_app().get_build_version(),
                "experiment": str(_setting("experiment", "")), "condition": str(_setting("condition", "")),
                "station_cycle_s": self._sim.config.process.cycle_s if self._sim.config.process else None,
                "part": self._catalog.part, "lighting_condition": _lighting(), "camera_resolution": list(L.CAMERA_RESOLUTION),
                "vision": _vision_on(),
                "inspector": self._inspector.config.__dict__ if self._inspector else None,
                "views": [v.name for v in self._cell.cycle.views] if self._cell else None,
                "decision": str(_setting("decision", "rules")),
                "inspector_model": self._model.card.extra.get("name") if self._model else None,
                "view_inspectors": [i.config.__dict__ for i in self._inspectors] if self._cell else None}
        with open(os.path.join(self.run_dir, "run.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        self._run_id = run_id
        self._run_t0 = time.perf_counter()
        self._runtime.open(self.run_dir, run_id, bool(_setting("trace", False)))
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
        inspected, views = [], []
        for e in self._sim.step(dt):
            p = self._sim.tracker.get(e.product_id)
            if e.kind == SPAWN:
                scene.spawn_product_prim(stage, p.product_id, p.defect_kind, p.x,
                                         self._catalog.variant_path(p.ground_truth, p.defect_kind),
                                         self._catalog.raw_path(p.ground_truth, p.defect_kind))
            elif e.kind == UNLOAD:
                scene.show_final_shape(stage, p.product_id)
                scene.set_product_pose(stage, p.product_id, self._belt_pose(p.x))
            elif e.kind == VIEW:
                views.append((p.product_id, e.index))
            elif e.kind == INSPECT and not _vision_on():
                if self._events is not None:  # keeps the INSPECT/VISION audit consistent
                    self._events.write(e.time, p.product_id, "VISION", detail="skipped (vision off)")
            elif e.kind == INSPECT and self._cell is None:  # the cell takes its pictures at VIEW
                inspected.append(p.product_id)
            elif e.kind == REJECT:
                self._anims[p.product_id] = e.time
            elif e.kind == EXIT and p.exit_route == "pass":
                scene.remove_product_prim(stage, p.product_id)
            reason = ""
            if e.kind in (REJECT, SORT):
                reason = f" ({self._sorter.decisions[p.product_id].reason})"
            if e.kind == VIEW:
                reason = f" {e.index + 1}/{len(self._inspectors) or '?'}"
            msg = f"t={e.time:7.3f}s id={e.product_id:04d} {e.kind}{reason}"
            print(f"{LOG_PREFIX} {msg}")
            self._ui.set_last_event(msg)
            if self._events is not None:
                self._events.write(e.time, e.product_id, e.kind, e.x, e.station,
                                   str(e.index) if e.kind == VIEW else reason.strip(" ()"))
        for p in self._sim.tracker.on_belt():
            scene.move_product_prim(stage, p.product_id, p.x, rest_dz=self._rest_dz)
        self._animate_rejects(stage, finish=False)
        if self._cell is not None:
            self._animate_cell(stage)
        if _setting("trace", False):
            self._runtime.mark("STATE_APPLIED")
        # Request frames after the prims (and the cell's camera) moved, so the captured render
        # shows this update's state.
        for pid in inspected:
            self._request_inspection(pid)
        for pid, k in views:
            self._request_view(pid, k)
        self._refresh_counters()
        if self._sim.finished:
            self._animate_rejects(stage, finish=True)
            self.stop()
            self._ui.set_status("finished - writing results")
            self._runtime.tasks.create(self._finalize_run_async())

    @staticmethod
    def _belt_pose(x: float) -> np.ndarray:
        m = np.eye(4)
        m[:3, 3] = (x, 0.0, L.CONVEYOR_TOP_Z + scene.PART_REST_DZ)
        return m

    def _station_time(self):
        """Seconds since the product in the cell was loaded, or None when the cell is empty."""
        pid = self._sim.station_product
        return None if pid is None else self._sim.time - self._sim.tracker.get(pid).load_time

    def _animate_cell(self, stage):
        """Inspection cell: pose the machine, then move the product with it.
        load: belt entry -> platter (transfer robot pick-and-place, or a lifted arc without the
        robot asset); views: rides the tilting/turning platter; unload: platter -> belt exit
        (stays there if the exit is still blocked). The robot waits between transfers."""
        t = self._station_time()
        self._cell.apply(t)
        if t is None:
            if self._arm is not None:
                self._arm.apply(self._arm.transfer.wait_pose())
            return
        cycle, st = self._cell.cycle, self._sim.config.process
        seat = self._cell.seat_pose()
        load_s, unload_s, u0 = cycle.timing.load_s, cycle.timing.unload_s, cycle.unload_start
        if t < load_s:
            pose = self._transfer_pose("load", t, self._belt_pose(st.x_entry), seat, t / load_s)
        elif t < u0:
            pose = seat
            if self._arm is not None:
                self._arm.apply(self._arm.transfer.wait_pose())
        else:
            pose = self._transfer_pose("unload", t - u0, seat, self._belt_pose(st.x_exit), (t - u0) / unload_s)
        scene.set_product_pose(stage, self._sim.station_product, pose)

    def _transfer_pose(self, phase, t, pick, place, k):
        """Product pose during a transfer; drives the robot when there is one."""
        if self._arm is None:
            return self._lift_lerp(pick, place, k, L.TRANSFER_LIFT)
        q, carried, where = self._arm.transfer.state(phase, t)
        self._arm.apply(q)
        if carried is not None:
            return carried
        return pick if where == "before" else place

    @staticmethod
    def _lift_lerp(a: np.ndarray, b: np.ndarray, k: float, lift: float = 0.12) -> np.ndarray:
        """Translation lerp with a parabolic lift (pick-and-place); rotation from the nearer end."""
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
        self._runtime.capture(product_id, 0,
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
        self._runtime.mark("VERDICT_LATE" if self._sorter.is_sorted(product_id) else "VERDICT_APPLIED",
                           detail="capture failed -> unknown")
        self._refresh_counters()

    def _request_view(self, product_id: int, view: int, retake: bool = False):
        """Inspection cell: capture view `view` of the product on the platter (camera in place)."""
        if self._frames is None or not self._inspectors:
            return
        p = self._sim.tracker.get(product_id)
        if self._log and view == 0 and not retake:
            p.inspection_start_ms = self._run_ms()
        sim_time, speed = self._sim.time, self._sim.config.speed
        self._runtime.capture(product_id, view,
            lambda rgb, cap_ms, stale, offset: self._on_view_frame(product_id, view, rgb, cap_ms, stale, offset,
                                                                  sim_time, speed, retake),
            on_error=lambda msg: self._on_view_error(product_id, view, msg, sim_time, speed))

    def _vet(self, result, product_id, stale, frame_offset):
        """Never attach an image that may not show this product's requested state."""
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
        return result

    def _record(self, product_id, view, result, capture_ms, frame_offset, sim_time, speed, frame_file, model=None):
        if not self._log:
            return
        p = self._sim.tracker.get(product_id)
        self._log.append(InspectionRecord(
            run_id=self._run_id, seed=self._sim.config.seed, product_id=product_id, view=view,
            ground_truth=p.ground_truth,  # evaluation only, copied from the tracker
            predicted_label=result.label, defect_reason=result.defect_reason,
            score=round(result.score, 4), mean_hue=round(result.mean_hue, 2), area_px=result.area_px,
            interior_ratio="" if math.isnan(result.interior_ratio) else round(result.interior_ratio, 4),
            interior_bright="" if math.isnan(result.interior_bright) else round(result.interior_bright, 4),
            capture_latency_ms=round(capture_ms, 2), frame_offset="" if frame_offset is None else frame_offset,
            inspection_latency_ms=round(result.latency_ms, 3),
            simulation_time_s=round(sim_time, 3), conveyor_speed=speed,
            lighting_condition=_lighting(), frame_file=frame_file or "", reason=result.reason,
            model_label=model.label if model else "", model_score=round(model.score, 4) if model else "",
            model_view=(model.decided_by or "") if model else "",
            model_latency_ms=round(model.latency_ms, 3) if model else ""))

    def _apply_verdict(self, product_id, result, sim_time):
        """The product's final vision verdict (applied unless it was already sorted)."""
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
        self._runtime.mark("VERDICT_LATE" if self._sorter.is_sorted(product_id) else "VERDICT_APPLIED",
                           detail=result.label)
        msg = f"id={product_id:04d} vision={result.label} score={result.score:.2f} ({result.latency_ms:.1f} ms)"
        print(f"{LOG_PREFIX} {msg}")
        self._ui.set_last_event(msg)
        if self._events is not None:
            self._events.write(sim_time, product_id, "VISION", detail=f"{result.label} {result.defect_reason}".strip())
        self._refresh_counters()

    def _on_frame(self, product_id, rgb, capture_ms, stale, frame_offset, sim_time, speed):
        result = self._vet(self._inspector.inspect(rgb), product_id, stale, frame_offset)  # pixels only
        self._runtime.mark("INSPECTION_DONE", detail="rules")
        frame_file = self._log.save_frame(product_id, rgb) if self._log else None
        self._record(product_id, 0, result, capture_ms, frame_offset, sim_time, speed, frame_file)
        self._apply_verdict(product_id, result, sim_time)

    def _can_retake(self, product_id, view) -> bool:
        """Still holding still for this view of this product (so a new frame shows the same pose)."""
        t = self._station_time()
        return self._sim.station_product == product_id and t is not None and self._cell.cycle.view_at(t) == view

    def _on_view_frame(self, product_id, view, rgb, capture_ms, stale, frame_offset, sim_time, speed, retake=False):
        # In the cell consecutive captures always differ in pose (another view or another product),
        # so identical pixels mean the render did not show the requested state, even with a matching
        # frame number (seen once in 150 captures on 2026-10-23: view 1 = view 0 image). Retake once
        # while the machine still holds this view, else the view is unknown.
        if stale and not retake and self._can_retake(product_id, view):
            self._view_retakes += 1
            carb.log_warn(f"{LOG_PREFIX} id={product_id:04d} view {view} identical to the previous capture -> retake")
            self._request_view(product_id, view, retake=True)
            return
        result = self._vet(self._inspectors[view].inspect(rgb), product_id, False, frame_offset)  # pixels only
        if stale:
            self._stale_frames += 1
            result.label, result.reason = UNKNOWN, "stale frame (identical to the previous capture, camera moved)"
            carb.log_warn(f"{LOG_PREFIX} id={product_id:04d} view {view} stale frame -> unknown")
        self._runtime.mark("INSPECTION_DONE", detail="rules")
        frame_file = self._log.save_frame(product_id, rgb, view) if self._log else None
        self._record(product_id, view, result, capture_ms, frame_offset, sim_time, speed, frame_file)
        self._view_done(product_id, view, result, capture_ms, sim_time, speed, rgb)

    def _on_view_error(self, product_id, view, message, sim_time, speed):
        carb.log_warn(f"{LOG_PREFIX} id={product_id:04d} view {view} capture failed ({message}) -> unknown")
        result = InspectionResult(UNKNOWN, 0.0, 0, float("nan"), None, 0.0, f"capture failed: {message}")
        self._record(product_id, view, result, 0.0, None, sim_time, speed, "")
        self._view_done(product_id, view, result, 0.0, sim_time, speed)

    def _view_done(self, product_id, view, result, capture_ms, sim_time, speed, rgb=None):
        """Collect the views of a product; with all of them, combine the rule verdicts, run the
        learned inspector on the same frames, record both and apply the configured decision."""
        got = self._view_results.setdefault(product_id, {})
        got[view] = (result, capture_ms, rgb)
        names = [v.name for v in self._cell.cycle.views]
        if len(got) < len(names):
            return
        del self._view_results[product_id]
        combined = combine_views([got[k][0] for k in range(len(names))], names)
        model = None
        if self._model is not None:
            # Frames that were not verified (mismatch, stale, failed capture) are not judged at all.
            unusable = any(got[k][2] is None or got[k][0].reason.startswith(("frame mismatch", "stale", "capture failed"))
                           for k in range(len(names)))
            if unusable:
                from .core.model_inspector import ModelVerdict

                model = ModelVerdict(UNKNOWN, float("nan"), [], None, 0.0)
            else:
                model = self._model.judge([got[k][2] for k in range(len(names))])
        self._record(product_id, "all", combined, max(g[1] for g in got.values()), 0, sim_time, speed, "", model)
        verdict = combined
        if model is not None and str(_setting("decision", "rules")) == "model":
            verdict = InspectionResult(model.label, 0.0 if math.isnan(model.score) else model.score, combined.area_px,
                                       combined.mean_hue, None, model.latency_ms,
                                       f"model p(defect)={model.score:.3f} (view {model.decided_by})")
            verdict.defect_reason = "model" if model.label == "defect" else ""
        self._apply_verdict(product_id, verdict, sim_time)

    # -- run results ------------------------------------------------------

    async def _finalize_run_async(self):
        """Write results.csv + summary.json once every pending frame has been handled."""
        app = omni.kit.app.get_app()
        generation = self._runtime.generation
        for _ in range(600):
            if not self._runtime.valid(generation):
                return
            if self.pending_frames == 0:
                break
            await app.next_update_async()
        if not self._runtime.valid(generation):
            return
        incomplete = self.pending_frames > 0
        if self._frames:
            if incomplete:
                self._frames.cancel_pending()
            await self._frames.drain()
        if not self._runtime.valid(generation):
            return
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
            "status": "capture_drain_timeout" if incomplete else "complete",
            "run_id": self._run_id,
            "products": len(products),
            "sorted": len(sorted_rows),
            "sort_correct": sum(r["sort_correct"] is True for r in sorted_rows),
            "rejected": sum(r["sort_result"] == "reject" for r in sorted_rows),
            "fail_safe_rejects": sum("fail-safe" in r["sort_reason"] for r in sorted_rows),
            "late_results": len(self._sorter.late_results),
            "frame_mismatches": self._frame_mismatches,
            "stale_frames": self._stale_frames,
            "view_retakes": getattr(self, "_view_retakes", 0),
            "vision": _vision_on(),
            "frame_target_misses": self._frames.frame_target_misses if self._frames else None,
            "capture_timeouts": self._frames.timeouts if self._frames else None,
            "not_exited": sum(p.state != ProductState.EXITED for p in products),
            "pending_frames_at_finalize": self.pending_frames,
            "simulation_time_s": round(self._sim.time, 3),
            "part": self._catalog.part,
            "throughput_per_hour": round(len(sorted_rows) / self._sim.time * 3600.0, 1) if self._sim.time else None,
        }
        if self._sim.config.process is not None:  # inspection cell line metrics
            st = self._sim.config.process
            self.summary["line"] = {
                "station": st.name, "cycle_s": round(st.cycle_s, 3), "views": len(st.view_times),
                "spawn_interval_s": self._sim.config.spawn_interval,
                "station_utilization": round(self._sim.station_utilization, 4),
                "station_busy_s": round(self._sim.station_busy_time, 3),
                "station_exit_blocked_s": round(self._sim.station_blocked_time, 3),
                "queue_max": self._sim.queue_max,
                "queue_mean": round(self._sim.queue_mean, 3),
            }
        if self._runtime.trace:
            self._runtime.trace.close(self._sim.time, self.summary["status"])
            self.summary["timing"] = self._runtime.trace.summary(self._sim.time)
            wall_s = self.summary["timing"]["wall_s"]
            self.summary["wall_throughput_per_hour"] = len(sorted_rows) / wall_s * 3600 if wall_s else None
        with open(os.path.join(self.run_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(self.summary, f, indent=2)
        self.run_complete = True
        if self.summary["vision"]:
            self._ui.set_status(f"finished: sorted {self.summary['sort_correct']}/{self.summary['sorted']} correct")
        else:  # nothing was inspected, so "correct" against the hidden ground truth means nothing here
            self._ui.set_status(f"finished: {self.summary['sorted']} passed (vision off)")
        print(f"{LOG_PREFIX} summary {json.dumps(self.summary)}")

    def _cell_status(self) -> str:
        pid, t = self._sim.station_product, self._station_time()
        if self._cell is None or pid is None:
            return "idle"
        return f"{self._cell.phase(t)} id={pid:04d}"

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
            + (f"vision: good={n_pred['good']} defect={n_pred['defect']} unknown={n_pred['unknown']}\n"
               if _vision_on() else "vision: off (every product passes)\n")
            + f"sorted: pass={n_pass} reject={n_rej}"
            + (f" correct={n_ok}/{len(d)}  " if _vision_on() else "  ")  # no verdicts: "correct" is meaningless
            + f"late={len(self._sorter.late_results)} frame_err={getattr(self, '_frame_mismatches', 0)}"
            + (f"\ncell: {self._cell_status()}"
               f"  queue={self._sim.queue_len} (max {self._sim.queue_max})"
               f"  util={self._sim.station_utilization * 100:.0f}%"
               if self._sim.config.process is not None else "")
        )
