"""Kit startup script (run with kit --exec): build the factory, run one full line run
with vision inspection enabled, wait for all frames, then quit.
The run (frames/*.png, inspections.csv, run.json) is written under results/runs/.
Used by scripts/collect_frames.ps1. Seed / product count / speed come from
--/exts/visiontwin.factory/{seed,maxProducts,speed}.
"""

import asyncio
import traceback

import carb
import omni.kit.app
from omni.kit.viewport.utility import get_active_viewport

TAG = "[collect_frames]"


async def _wait_for(cond, app, max_frames):
    for _ in range(max_frames):
        value = cond()
        if value:
            return value
        await app.next_update_async()
    raise TimeoutError(f"timed out after {max_frames} frames")


async def _main():
    app = omni.kit.app.get_app()
    code = 1
    try:
        import visiontwin.factory.extension as vt

        ext = await _wait_for(vt.get_instance, app, 3000)
        await _wait_for(get_active_viewport, app, 3000)
        await ext.build_scene_async()
        # Give the inspection viewport time to start rendering before the first product arrives.
        for _ in range(120):
            await app.next_update_async()
        ext.start()
        # run_complete is set after the line finished AND every pending frame was handled
        # (results.csv / summary.json written).
        await _wait_for(lambda: ext.run_complete, app, 60 * 60 * 10)
        if ext.summary and ext.summary.get("status", "complete") != "complete":
            raise RuntimeError(f"incomplete run: {ext.summary['status']}")
        print(f"{TAG} summary: {ext.summary}")
        print(f"{TAG} done: run_dir={ext.run_dir}")
        code = 0
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
