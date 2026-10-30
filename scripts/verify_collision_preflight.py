"""Kit integration: normal crown build/start, injected obstacle blocking, rebuild recovery.

Used by verify_collision_preflight.ps1. Injection exists only in this test process.
Exit 0 on all assertions; failure.json and nonzero exit otherwise.
"""

import asyncio
import importlib
import json
from pathlib import Path
import traceback

import carb
import carb.settings
import omni.kit.app


async def main():
    app = omni.kit.app.get_app()
    out = Path(carb.settings.get_settings().get("/visiontwin/interview/out"))
    checks, code = {}, 1
    try:
        vt = importlib.import_module("visiontwin.factory.extension")
        checker = importlib.import_module("visiontwin.factory.collision_check")
        collision = importlib.import_module("visiontwin.factory.core.collision")
        scene = importlib.import_module("visiontwin.factory.scene_manager")
        for _ in range(1800):
            ext = vt.get_instance()
            if ext is not None:
                break
            await app.next_update_async()
        assert ext is not None
        await ext.build_scene_async()
        assert ext._arm is not None and ext._scene_ready
        assert ext.collision_report["status"] == "clear_at_samples"
        checks["baseline"] = ext.collision_report
        ext.start()
        assert ext._sim.running
        await app.next_update_async()
        ext.stop()
        checks["clear_scene_starts"] = True

        original = checker.check_cell

        def with_obstacle(stage, arm, cell, **kwargs):
            q, _, _ = arm.transfer.state("load", 0.5)
            tool = arm.transfer.arm.tool(q)
            scene._box(stage, "/World/Factory/InjectedObstacle", tuple(tool[:3, 3]),
                       (0.06, 0.06, 0.06), (1, 0, 0))
            return original(stage, arm, cell, **kwargs)

        checker.check_cell = with_obstacle
        try:
            try:
                await ext.build_scene_async()
            except collision.CollisionBlocked:
                pass
            else:
                raise AssertionError("injected obstacle must block Build Scene")
            assert not ext._scene_ready and not ext._sim.running
            ext.start()
            assert not ext._sim.running and ext._update_sub is None
            checks["blocked"] = ext.collision_report
            checks["blocked_scene_cannot_start"] = True
        finally:
            checker.check_cell = original
        await ext.build_scene_async()
        assert ext._scene_ready and ext.collision_report["status"] == "clear_at_samples"
        ext.start()
        assert ext._sim.running
        ext.stop()
        checks["rebuild_recovers"] = True
        (out / "report.json").write_text(json.dumps(dict(passed=True, checks=checks), indent=2), encoding="utf-8")
        print("[collision_preflight] PASS normal start, obstacle blocking, blocked Start, rebuild recovery")
        code = 0
    except Exception:
        error = traceback.format_exc()
        (out / "failure.json").write_text(json.dumps(dict(checks=checks, error=error), indent=2), encoding="utf-8")
        carb.log_error(error)
    finally:
        app.post_quit(code)


asyncio.ensure_future(main())
