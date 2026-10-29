"""Render an update-coded binary marker in a dedicated diagnostic stage.

Invoked by probe_frame_content.ps1. This scene never feeds the inspection model.
Outputs: report.json with requested/returned/decoded frame numbers and sample PNGs.
"""

import asyncio
import json
from pathlib import Path
import traceback

import carb
import carb.eventdispatcher
import carb.settings
import numpy as np
import omni.kit.app
import omni.usd
from omni.kit.viewport.utility import get_active_viewport, next_viewport_frame_async
from pxr import Gf, Sdf, UsdGeom, UsdShade


async def main():
    app = omni.kit.app.get_app()
    out = Path(carb.settings.get_settings().get("/visiontwin/interview/out"))
    observer = provider = None
    code = 1
    try:
        from visiontwin.factory.frame_provider import InspectionFrameProvider
        await omni.usd.get_context().new_stage_async()
        stage = omni.usd.get_context().get_stage()
        UsdGeom.SetStageMetersPerUnit(stage, 1)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        markers = []
        for i in range(12):
            tile = UsdGeom.Cube.Define(stage, f"/Marker/B{i}")
            tile.CreateSizeAttr(1)
            xf = UsdGeom.XformCommonAPI(tile)
            xf.SetScale(Gf.Vec3f(0.075,0.16,0.01))
            xf.SetTranslate(Gf.Vec3d(-0.55 + i*0.1, 0, 0))
            mat = UsdShade.Material.Define(stage, f"/Looks/M{i}")
            shader = UsdShade.Shader.Define(stage, f"/Looks/M{i}/Surface")
            shader.CreateIdAttr("UsdPreviewSurface")
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0))
            value = shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f)
            value.Set(Gf.Vec3f(4))
            markers.append(xf)
            mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
            UsdShade.MaterialBindingAPI.Apply(tile.GetPrim()).Bind(mat)
        camera = UsdGeom.Camera.Define(stage, "/Camera")
        camera.CreateProjectionAttr(UsdGeom.Tokens.orthographic)
        camera.CreateHorizontalApertureAttr(12)
        camera.CreateVerticalApertureAttr(3)
        UsdGeom.XformCommonAPI(camera).SetTranslate(Gf.Vec3d(0,0,2))
        main_viewport = get_active_viewport()
        assert main_viewport is not None
        main_viewport.camera_path = "/Camera"
        # Wait for actual main-viewport frames before creating the second Hydra engine.
        await next_viewport_frame_async(main_viewport, 60)
        provider = InspectionFrameProvider("/Camera", (960,240))
        await provider.ready_async()
        def read_means(rgb):
            return [float(np.mean(rgb[100:140, int((i+0.5)*80)-8:int((i+0.5)*80)+8])) for i in range(12)]
        def place(bit, on):
            markers[bit].SetTranslate(Gf.Vec3d(-0.55 + bit*0.1, 0 if on else 10, 0))
        async def calibrate(value):
            for bit in range(12):
                place(bit, bool(value))
            for _ in range(30):
                await app.next_update_async()
            images, errors = [], []
            provider.request_frame(lambda rgb, *args: images.append(rgb), errors.append)
            for _ in range(300):
                if images or errors:
                    break
                await app.next_update_async()
            assert images and not errors, errors
            import cv2
            cv2.imwrite(str(out / ("white.png" if value else "black.png")), cv2.cvtColor(images[0], cv2.COLOR_RGB2BGR))
            return read_means(images[0])
        black, white = await calibrate(0), await calibrate(4)
        assert all(w-b > 50 for b,w in zip(black,white)), (black,white)
        samples, requested = [], [0]
        def update(_event):
            frame = app.get_update_number()
            for i in range(12):
                place(i, (frame >> i) & 1)
            if frame % 15 or requested[0] >= 30:
                return
            requested[0] += 1
            def received(rgb, latency, stale, offset):
                means = read_means(rgb)
                normalized = [(v-b)/(w-b) for v,b,w in zip(means,black,white)]
                uncertain = any(0.35 < v < 0.65 for v in normalized)
                decoded = sum((v >= 0.5) << i for i,v in enumerate(normalized))
                sample = dict(requested_frame=frame, returned_frame=None if offset is None else frame+offset,
                              expected_code=frame % 4096, decoded_code=decoded, undecodable=uncertain,
                              matches=None if uncertain else decoded == frame % 4096,
                              means=means, latency_ms=latency, identical_pixels=stale)
                samples.append(sample)
                if len(samples) == 1 or sample["matches"] is False:
                    import cv2
                    cv2.imwrite(str(out / f"marker_{frame}.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            provider.request_frame(received, on_error=lambda msg: samples.append(dict(requested_frame=frame, error=msg)))
        observer = carb.eventdispatcher.get_eventdispatcher().observe_event(
            observer_name="visiontwin.interview.marker", event_name=omni.kit.app.GLOBAL_EVENT_UPDATE, on_event=update)
        for _ in range(2400):
            if requested[0] == 30 and provider.pending == 0:
                break
            await app.next_update_async()
        assert len(samples) == 30, f"only {len(samples)}/30 callbacks"
        report = dict(samples=samples, mismatches=sum(s.get("matches") is False for s in samples),
                      undecodable=sum(s.get("undecodable",False) for s in samples),
                      errors=sum("error" in s for s in samples),
                      calibration=dict(black=black, white=white),
                      note="dedicated transform-coded emissive marker scene; no production inspection or model inputs")
        (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[frame_content] samples=30 mismatches={report['mismatches']} undecodable={report['undecodable']} errors={report['errors']}")
        code = 0
    except Exception:
        carb.log_error(traceback.format_exc())
    finally:
        if observer:
            observer.reset()
        if provider:
            provider.destroy()
        app.post_quit(code)


asyncio.ensure_future(main())
