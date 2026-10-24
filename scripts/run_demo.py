"""Kit startup script (run with kit --exec): demo mode for screen recording. The app stays open.
Used by scripts/run_demo.ps1.

Builds the crown line with vision on, shows the overview, starts the line and switches the
main viewport by what the inspection cell does:
  robot loading / unloading      -> cell close-up
  machine moving / taking views  -> spindle camera
  otherwise                      -> overview (belts, reject pusher, bin)
After the last product the line stops, the teach pendant opens and plays origin + 5 faces.
The camera choice only follows the simulation state; it changes nothing in the run.

Settings: --/visiontwin/demo/products=4  --/visiontwin/demo/seed=42  --/visiontwin/demo/introUpdates=240
"""

import asyncio
import traceback

import carb
import carb.settings
import omni.kit.app
from omni.kit.viewport.utility import get_active_viewport

TAG = "[demo]"
OVERVIEW, CELL, SPINDLE = 0, 1, 2


async def _wait_for(get, app, frames=3000):
    for _ in range(frames):
        v = get()
        if v:
            return v
        await app.next_update_async()
    raise TimeoutError("startup")


def _view_for(ext) -> int:
    t = ext._station_time()
    if ext._cell is None or t is None:
        return OVERVIEW
    phase = ext._cell.phase(t)
    if phase in ("LOADING", "UNLOADING"):
        return CELL
    return SPINDLE  # VIEW k/5 and the moves between views


async def _main():
    app = omni.kit.app.get_app()
    s = carb.settings.get_settings()
    try:
        import visiontwin.factory.extension as vt

        ext = await _wait_for(vt.get_instance, app)
        await _wait_for(get_active_viewport, app)
        for key, value in (("part", "crown"), ("vision", True), ("defectRate", 0.3),
                           ("seed", int(s.get("/visiontwin/demo/seed") or 42)),
                           ("maxProducts", int(s.get("/visiontwin/demo/products") or 4))):
            s.set(f"/exts/visiontwin.factory/{key}", value)
        await ext.build_scene_async()
        ext.set_view(OVERVIEW)
        print(f"{TAG} scene ready: overview")
        for _ in range(int(s.get("/visiontwin/demo/introUpdates") or 240)):
            await app.next_update_async()
        ext.start()
        print(f"{TAG} line started")
        current = OVERVIEW
        while not ext.run_complete:
            view = _view_for(ext)
            if view != current:
                ext.set_view(view)
                current = view
            await app.next_update_async()
        ext.set_view(OVERVIEW)
        print(f"{TAG} line finished: {ext.summary and ext.summary.get('sort_correct')}/"
              f"{ext.summary and ext.summary.get('sorted')} sorted correctly")
        for _ in range(180):
            await app.next_update_async()
        pendant = ext.open_teach_pendant()
        if pendant is not None:
            pendant.generate()
            pendant.play()
            print(f"{TAG} teaching: origin + 5 faces")
            while pendant.playing:
                await app.next_update_async()
        print(f"{TAG} done (the app stays open; close it when the recording is finished)")
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")


asyncio.ensure_future(_main())
