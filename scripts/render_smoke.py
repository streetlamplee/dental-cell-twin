"""Kit startup script (run with kit --exec): build the factory, run the line briefly,
save a viewport PNG, then quit. Used by scripts/render_smoke.ps1.

Settings (pass as --/visiontwin/smoke/<name>=<value>):
  out      output PNG path (required)
  frames   update frames to run the conveyor before capturing (default 240)
"""

import asyncio
import traceback

import carb
import carb.settings
import omni.kit.app
from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport, next_viewport_frame_async

TAG = "[render_smoke]"


async def _wait_for(get, app, max_frames=3000):
    for _ in range(max_frames):
        value = get()
        if value:
            return value
        await app.next_update_async()
    raise TimeoutError("timed out waiting for startup")


def _print_stage_info(viewport):
    from pxr import UsdGeom

    stage = viewport.stage
    cam = stage.GetPrimAtPath(viewport.camera_path)
    xf = UsdGeom.Xformable(cam).ComputeLocalToWorldTransform(0)
    print(f"{TAG} upAxis={UsdGeom.GetStageUpAxis(stage)} metersPerUnit={UsdGeom.GetStageMetersPerUnit(stage)}")
    print(f"{TAG} camera={viewport.camera_path} pos={xf.ExtractTranslation()}")
    cache = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
    for path in ("/World/Factory/Floor", "/World/Factory/Conveyor", "/World/Products",
                 "/World/Factory/MillStation/Mill"):
        prim = stage.GetPrimAtPath(path)
        rng = cache.ComputeWorldBound(prim).ComputeAlignedRange() if prim else None
        print(f"{TAG} bbox {path}: {rng}")
    products = stage.GetPrimAtPath("/World/Products")
    first = products.GetChildren()[0] if products and products.GetChildren() else None
    if first:
        for prim in [first] + [p for p in first.GetChildren()][:1]:
            xf = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(0)
            print(f"{TAG} product {prim.GetPath()} bbox {cache.ComputeWorldBound(prim).ComputeAlignedRange()} "
                  f"scale~{xf.GetRow3(0).GetLength():.5f} ops={[op.GetOpName() for op in UsdGeom.Xformable(prim).GetOrderedXformOps()]}")


async def _main():
    app = omni.kit.app.get_app()
    settings = carb.settings.get_settings()
    out = settings.get("/visiontwin/smoke/out")
    frames = int(settings.get("/visiontwin/smoke/frames") or 240)
    code = 1
    try:
        import visiontwin.factory.extension as vt
        from visiontwin.factory.core import layout as L

        ext = await _wait_for(vt.get_instance, app)
        viewport = await _wait_for(get_active_viewport, app)
        print(f"{TAG} extension and viewport ready")

        await ext.build_scene_async()
        ext.start()
        for _ in range(frames):
            await app.next_update_async()
        ext.stop()
        print(f"{TAG} sim time {ext._sim.time:.2f}s, products {len(ext._sim.tracker)}")
        _print_stage_info(viewport)

        # Overview image, then the same frame through the inspection camera.
        results = []
        shots = [(None, out), (L.CAMERA_PATH, out.replace(".png", "_inspection.png"))]
        if viewport.stage.GetPrimAtPath(L.MILL_CAMERA_PATH):
            shots.insert(1, (L.MILL_CAMERA_PATH, out.replace(".png", "_mill.png")))
        for cam_path, path in shots:
            if cam_path:
                viewport.camera_path = cam_path
            await next_viewport_frame_async(viewport, 30)  # let RTX converge a little
            cap = capture_viewport_to_file(viewport, path)
            result = await cap.wait_for_result(completion_frames=60)
            print(f"{TAG} capture camera={viewport.camera_path} result={result} -> {path}")
            results.append(bool(result))
        code = 0 if all(results) else 2
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
