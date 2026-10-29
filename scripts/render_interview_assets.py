"""Measure a generated USD fixture in Kit, save render proof and update intervals.

Invoked by benchmark_interview_render.ps1. Settings: /visiontwin/interview/{scene,out}.
Outputs: render.json and frame.png; process startup is measured separately by the launcher.
"""

import asyncio
import json
from pathlib import Path
import sys
import time
import traceback

import carb
import carb.settings
import omni.kit.app
import omni.usd
from pxr import Gf, Usd, UsdGeom, UsdLux
from omni.kit.viewport.utility import (get_active_viewport, get_active_viewport_window,
                                      next_viewport_frame_async, capture_viewport_to_file)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _interview_metrics import process_memory, gpu_memory


async def main():
    app = omni.kit.app.get_app()
    settings = carb.settings.get_settings()
    out = Path(settings.get("/visiontwin/interview/out"))
    code = 1
    try:
        path = settings.get("/visiontwin/interview/scene")
        start = time.perf_counter()
        success, error = await omni.usd.get_context().open_stage_async(path)
        if not success:
            raise RuntimeError(error)
        opened = time.perf_counter()
        stage = omni.usd.get_context().get_stage()
        bounds = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_]).ComputeWorldBound(stage.GetPseudoRoot()).ComputeAlignedRange()
        centre = bounds.GetMidpoint()
        distance = max(0.2, bounds.GetSize().GetLength()*2.5)
        camera = UsdGeom.Camera.Define(stage, "/World/Camera")
        view = Gf.Matrix4d().SetLookAt(centre + Gf.Vec3d(0,-distance,distance), centre, Gf.Vec3d(0,0,1))
        UsdGeom.Xformable(camera).MakeMatrixXform().Set(view.GetInverse())
        camera.CreateFocalLengthAttr(50)
        camera.CreateHorizontalApertureAttr(24)
        camera.CreateVerticalApertureAttr(16)
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.001,10000))
        if not stage.GetPrimAtPath("/World/Light"):
            UsdLux.DomeLight.Define(stage, "/World/Light").CreateIntensityAttr(1000)
        viewport = get_active_viewport()
        assert viewport is not None
        viewport.camera_path = "/World/Camera"
        # GUI lighting rig is excluded from this fixture's fixed light setup.
        from omni.kit.actions.core import execute_action
        execute_action("omni.kit.viewport.menubar.lighting", "set_lighting_mode_stage")
        await next_viewport_frame_async(viewport, 1)
        first = time.perf_counter()
        await next_viewport_frame_async(viewport, 3)
        widget = get_active_viewport_window().viewport_widget
        widget.fill_frame = False
        widget.expand_viewport = False
        widget.set_resolution((960,640))
        viewport.resolution_scale = 1.0
        await next_viewport_frame_async(viewport, 3)
        fixed_resolution_first = time.perf_counter()
        assert tuple(viewport.resolution) == (960,640), viewport.resolution
        for _ in range(60):
            await app.next_update_async()
        memory = process_memory()
        gpu = gpu_memory()  # outside the timing window
        samples = []
        previous = time.perf_counter()
        for _ in range(120):
            await app.next_update_async()
            now = time.perf_counter()
            samples.append((now - previous)*1000)
            previous = now
        capture = capture_viewport_to_file(viewport, str(out / "frame.png"))
        await capture.wait_for_result()
        stage = omni.usd.get_context().get_stage()
        report = dict(scene=path, stage_open_s=opened-start, first_viewport_frame_s=first-start,
                      usd_version=Usd.GetVersion(), kit_version=app.get_build_version(),
                      first_fixed_resolution_frame_s=fixed_resolution_first-start,
                      camera_fit=dict(centre=list(centre), distance=distance, focal_mm=50, aperture_mm=[24,16]),
                      update_ms=samples, memory=memory, gpu=gpu, resolution=list(viewport.resolution),
                      warmup_updates=60, measured_updates=120, viewport_frame_info=dict(viewport.frame_info),
                      prototype_count=len(stage.GetPrototypes()),
                      measure="synchronous Kit app update intervals; includes CPU and rendering, not GPU-only duration",
                      cache="fresh Kit process; driver and OS caches not cleared")
        (out / "render.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"[interview_render] PASS: {out}")
        code = 0
    except Exception:
        carb.log_error(traceback.format_exc())
    finally:
        app.post_quit(code)


asyncio.ensure_future(main())
