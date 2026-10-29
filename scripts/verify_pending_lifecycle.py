"""Stress real scheduled captures across Reset/build/external Stage/toggle transitions.

Invoked by verify_pending_lifecycle.ps1. Records whether native readback already completed
before each transition, separately from the deliberately delayed Python delivery.
"""

import asyncio
import importlib
import json
import math
from pathlib import Path
import traceback

import carb
import carb.settings
import omni.kit.app
import omni.usd


async def pump(n):
    for _ in range(n):
        await omni.kit.app.get_app().next_update_async()


def current():
    return importlib.import_module("visiontwin.factory.extension").get_instance()


async def main():
    app = omni.kit.app.get_app()
    settings = carb.settings.get_settings()
    out = Path(settings.get("/visiontwin/interview/out"))
    rows, code = [], 1
    try:
        for _ in range(1800):
            if current() is not None:
                break
            await pump(1)
        ext = current()
        assert ext is not None
        await ext.build_scene_async()
        for scenario in ("reset", "build", "external_stage", "extension_toggle"):
            for repeat in range(10):
                provider = ext._frames
                provider._pool.delivery_delay_s = 2.0
                delivered = []
                provider.request_frame(lambda *args: delivered.append("frame"), lambda msg: delivered.append("error"))
                # Let the capture coroutine schedule native work without advancing the simulation.
                await asyncio.sleep(0)
                assert provider.pending == 1
                request = next(iter(provider._pool.requests.values()))
                assert request["native_scheduled"]
                was_received = request["native_received"]
                if scenario == "reset":
                    ext.reset()
                elif scenario == "build":
                    await ext.build_scene_async()
                elif scenario == "external_stage":
                    await omni.usd.get_context().new_stage_async()
                    assert not ext._scene_ready
                    await ext.build_scene_async()
                else:
                    manager = app.get_extension_manager()
                    ext_id = manager.get_enabled_extension_id("visiontwin.factory")
                    app_id = manager.get_enabled_extension_id("visiontwin.app")
                    manager.set_extension_enabled_immediate(ext_id, False)
                    await pump(2)
                    manager.set_extension_enabled_immediate(app_id or "visiontwin.factory", True)
                    await pump(60)
                    ext = current()
                    assert ext is not None
                    await ext.build_scene_async()
                await provider.drain()
                await pump(2)
                assert provider.pending == 0 and not provider._pool.owner.tasks
                assert not delivered and not provider._pool.owner.errors
                subscription_probe = None
                if scenario == "extension_toggle":
                    # Check the observable effect of subscriptions after reactivation:
                    # one fixed simulation step per app update, including repeated Start.
                    ext.start()
                    ext.start()
                    await pump(2)
                    sim_before, update_before = ext._sim.time, app.get_update_number()
                    await pump(20)
                    sim_delta = ext._sim.time - sim_before
                    update_delta = app.get_update_number() - update_before
                    ext.stop()
                    fixed_dt = float(settings.get("/exts/visiontwin.factory/fixedDt") or 1 / 60)
                    assert update_delta > 0 and math.isclose(sim_delta, update_delta * fixed_dt, abs_tol=1e-8)
                    subscription_probe = dict(sim_delta_s=sim_delta, app_update_delta=update_delta,
                                              fixed_dt=fixed_dt, one_step_per_update=True)
                    ext.reset()
                rows.append(dict(scenario=scenario, repeat=repeat, native_scheduled=True,
                    native_received_before_transition=was_received, delivery_after_transition=delivered,
                    pending=provider.pending, tasks=len(provider._pool.owner.tasks),
                    subscription_probe=subscription_probe))
                print(f"[pending_lifecycle] {scenario} {repeat+1}/10 PASS")
            ext._frames._pool.delivery_delay_s = 0
        (out / "report.json").write_text(json.dumps(dict(passed=True, rows=rows,
            native_callback_pending_before_transition=sum(not r["native_received_before_transition"] for r in rows)),indent=2),encoding="utf-8")
        code = 0
    except Exception:
        (out / "failure.json").write_text(json.dumps(dict(rows=rows,error=traceback.format_exc()),indent=2),encoding="utf-8")
        carb.log_error(traceback.format_exc())
    finally:
        app.post_quit(code)


asyncio.ensure_future(main())
