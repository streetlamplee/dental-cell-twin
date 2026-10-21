"""Kit startup script (run with kit --exec): Gate B probe.

Compares ways of getting rendered frames from the inspection camera and reports which
ones deliver a buffer callback within a frame budget. Used by scripts/probe_capture.ps1.
  A: the extension's InspectionFrameProvider (what the line actually uses)
  B: a fresh ViewportWindow from omni.kit.viewport.utility.create_viewport_window
History: on 2026-10-21 a bare ViewportWidget in omni.ui.Window failed (no frames) while
B worked, so InspectionFrameProvider was switched to a ViewportWindow.
Writes one PNG per working method next to --/visiontwin/probe/out (a .png path prefix).
"""

import asyncio
import traceback

import carb
import carb.settings
import omni.kit.app
from omni.kit.viewport.utility import (capture_viewport_to_buffer, create_viewport_window,
                                       get_active_viewport, next_viewport_frame_async)

TAG = "[probe_capture]"


async def _frames(app, n):
    for _ in range(n):
        await app.next_update_async()


async def _try_capture(name, viewport_api, out_png, app):
    import cv2

    from visiontwin.factory.frame_provider import capsule_to_rgb

    got = {}

    def cb(buffer, size, w, h, fmt):
        got["rgb"] = capsule_to_rgb(buffer, size, w, h, fmt)
        got["info"] = (w, h, str(fmt))

    try:
        await asyncio.wait_for(next_viewport_frame_async(viewport_api, 5), timeout=20)
        print(f"{TAG} {name}: viewport delivered frames")
    except asyncio.TimeoutError:
        print(f"{TAG} {name}: viewport did NOT deliver frames within 20s")
    capture_viewport_to_buffer(viewport_api, cb)
    for _ in range(300):
        if got:
            break
        await app.next_update_async()
    if not got:
        print(f"{TAG} {name}: RESULT no buffer callback")
        return False
    rgb = got["rgb"]
    cv2.imwrite(out_png, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    print(f"{TAG} {name}: RESULT ok {got['info']} mean={rgb.mean():.1f} -> {out_png}")
    return True


async def _measure_lag(viewport_api, app):
    """Render lag: compare the viewport's frame_info at request time with the captured
    frame's frame_info, over several app updates."""
    print(f"{TAG} frame_info keys: {sorted(viewport_api.frame_info.keys())}")
    for i in range(5):
        info_req = dict(viewport_api.frame_info)
        upd_req = app.get_update_number()
        cap = capture_viewport_to_buffer(viewport_api, lambda *a: None)
        n_updates = 0
        while not cap.done if hasattr(cap, "done") else False:
            await app.next_update_async()
            n_updates += 1
        await cap.wait_for_result()
        info_cap = cap.frame_info or {}
        print(f"{TAG} lag#{i}: request update={upd_req} swh={info_req.get('swh_frame_number')} | "
              f"captured swh={info_cap.get('swh_frame_number')} at update={app.get_update_number()} "
              f"fps={info_req.get('fps')}")
        await app.next_update_async()


async def _main():
    app = omni.kit.app.get_app()
    out = carb.settings.get_settings().get("/visiontwin/probe/out")
    code = 1
    try:
        import visiontwin.factory.extension as vt
        from visiontwin.factory.core import layout as L

        while vt.get_instance() is None or get_active_viewport() is None:
            await app.next_update_async()
        ext = vt.get_instance()
        await ext.build_scene_async()
        ext.start()
        await _frames(app, 200)  # a couple of products on the belt
        ext.stop()

        ok_a = await _try_capture("A InspectionFrameProvider", ext._frames.viewport_api,
                                  out.replace(".png", "_A.png"), app)

        await _measure_lag(ext._frames.viewport_api, app)

        win = create_viewport_window("VisionTwin Probe B", width=640, height=480, camera_path=L.CAMERA_PATH)
        await _frames(app, 30)
        ok_b = await _try_capture("B ViewportWindow", win.viewport_api, out.replace(".png", "_B.png"), app)
        print(f"{TAG} summary A={ok_a} B={ok_b}")
        code = 0
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
