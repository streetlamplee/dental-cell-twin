"""Kit verification of two retimed crown cycles with real five-view inspection.

Checks applied machine joint increments, stationary output product during return,
release/next-load ordering, all inspection frames and normal run completion.
"""

import asyncio
import csv
import importlib
import json
from pathlib import Path
import traceback

import carb
import carb.settings
import numpy as np
import omni.kit.app
import omni.usd
from pxr import UsdGeom


async def main():
    app = omni.kit.app.get_app()
    out = Path(carb.settings.get_settings().get("/visiontwin/interview/out"))
    report, code = {}, 1
    try:
        vt = importlib.import_module("visiontwin.factory.extension")
        scene = importlib.import_module("visiontwin.factory.scene_manager")
        for _ in range(3000):
            ext = vt.get_instance()
            if ext is not None:
                break
            await app.next_update_async()
        assert ext is not None
        await ext.build_scene_async()
        assert ext._scene_ready and ext._arm and ext._frames
        cycle = ext._cell.cycle
        assert abs(cycle.cycle_s - 16.024) < 1e-9
        for _ in range(120):
            await app.next_update_async()
        maximum = dict.fromkeys(cycle.velocity_limits, 0.0)
        previous = None
        samples = 0
        original = ext._cell.set_joints

        def observe(q, camera_offset=(0.0, 0.0, 0.0)):
            nonlocal previous, samples
            original(q, camera_offset)
            now = ext._sim.time
            if previous and now > previous[0]:
                for joint, limit in cycle.velocity_limits.items():
                    speed = abs(q[joint] - previous[1][joint]) / (now - previous[0])
                    maximum[joint] = max(maximum[joint], speed)
                    assert speed <= limit + 1e-7, (joint, now, speed, limit)
                samples += 1
            previous = (now, dict(q))

        ext._cell.set_joints = observe
        returning_products = set()
        return_samples = 0
        ext.start()
        for _ in range(18000):
            await app.next_update_async()
            t = ext._station_time()
            if t is not None and t >= cycle.return_start:
                pid = ext._sim.station_product
                returning_products.add(pid)
                prim = omni.usd.get_context().get_stage().GetPrimAtPath(scene.product_path(pid))
                actual = np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(0).ExtractTranslation())
                expected = ext._belt_pose(ext._sim.config.process.x_exit)[:3, 3]
                np.testing.assert_allclose(actual, expected, atol=1e-8)
                assert ext._cell.phase(t) == "RETURNING"
                return_samples += 1
            if ext.run_complete:
                break
        assert ext.run_complete and ext.summary.get("status", "complete") == "complete"
        assert len(returning_products) == 2 and return_samples > 0 and samples > 0
        rows = list(csv.DictReader((Path(ext.run_dir) / "events.csv").open(encoding="utf-8-sig", newline="")))
        loads = {r["product_id"]: float(r["sim_time_s"]) for r in rows if r["event"] == "LOAD"}
        unloads = {r["product_id"]: float(r["sim_time_s"]) for r in rows if r["event"] == "UNLOAD"}
        assert len(loads) == len(unloads) == 2
        for pid in loads:
            assert abs(unloads[pid] - loads[pid] - cycle.cycle_s) < 1e-4
        ordered = sorted(loads, key=loads.get)
        assert loads[ordered[1]] >= unloads[ordered[0]] - 1e-6
        inspections = list(csv.DictReader((Path(ext.run_dir) / "inspections.csv").open(encoding="utf-8-sig", newline="")))
        for pid in loads:
            frames = [r for r in inspections if r["product_id"] == pid and r["view"] != "all"]
            assert sorted(r["view"] for r in frames) == ["0", "1", "2", "3", "4"]
            assert all(r["frame_file"] and (Path(ext.run_dir) / r["frame_file"]).is_file() for r in frames)
            assert all(r["predicted_label"] in ("good", "defect") for r in frames)
        report = dict(passed=True, cycle_s=cycle.cycle_s, return_s=cycle.return_duration_s,
                      max_observed_velocity=maximum, velocity_limits=cycle.velocity_limits,
                      applied_samples=samples, return_samples=return_samples,
                      returning_products=sorted(returning_products), load_times=loads, unload_times=unloads,
                      inspection_rows=len(inspections), summary=ext.summary, run_dir=ext.run_dir,
                      collision_report=ext.collision_report)
        assert len(inspections) == 12
        (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("[retimed_cycle] PASS applied speeds, output pose, two full cycles and vision completion")
        code = 0
    except Exception:
        error = traceback.format_exc()
        (out / "failure.json").write_text(json.dumps(dict(report=report, error=error), indent=2), encoding="utf-8")
        carb.log_error(error)
    finally:
        app.post_quit(code)


asyncio.ensure_future(main())
