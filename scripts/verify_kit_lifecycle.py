"""Inject held callbacks and real pending captures across Kit lifecycle changes.

Invoked by verify_kit_lifecycle.ps1. Before mode records the existing routing defect;
after mode requires no stale verdicts, no retained owned tasks and no pending captures.
"""

import asyncio
import importlib
import importlib.util
import json
from pathlib import Path
import traceback
import sys

import carb
import carb.settings
import omni.kit.app
import omni.usd


def current():
    return importlib.import_module("visiontwin.factory.extension").get_instance()


async def updates(count):
    for _ in range(count):
        await omni.kit.app.get_app().next_update_async()


async def spawn(ext, directory):
    carb.settings.get_settings().set("/exts/visiontwin.factory/outputDir", str(directory))
    ext.reset()
    ext.start()
    await updates(1)
    ext.stop()
    assert ext._sim.tracker.get(1) is not None


async def main():
    app = omni.kit.app.get_app()
    settings = carb.settings.get_settings()
    out = Path(settings.get("/visiontwin/interview/out"))
    before = bool(settings.get("/visiontwin/interview/before"))
    repeats = int(settings.get("/visiontwin/interview/repeats") or 10)
    code, rows = 1, []
    try:
        while current() is None:
            await updates(1)
        ext = current()
        if before:
            ext.on_shutdown()
            snapshot = Path(settings.get("/visiontwin/interview/beforeSource"))
            def load(name, file):
                spec = importlib.util.spec_from_file_location(name, snapshot / file)
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                return module
            load("visiontwin.factory.frame_provider", "frame_provider.py")
            old = load("visiontwin.factory.extension_before", "extension.py")
            ext = old.VisionTwinFactoryExtension()
            ext.on_startup("visiontwin.factory.before_snapshot")
        await ext.build_scene_async()
        scenarios = ("reset",) if before else ("reset", "build", "external_stage", "extension_toggle")
        for scenario in scenarios:
            for repeat in range(repeats):
                await spawn(ext, out / f"{scenario}_{repeat}_old")
                provider = ext._frames
                held = []
                original = provider.request_frame
                def hold(on_frame, on_error=None, **kw):
                    held.append((on_frame, on_error))
                provider.request_frame = hold
                ext._request_inspection(1)
                provider.request_frame = original
                assert len(held) == 1
                old_runtime = getattr(ext, "_runtime", None)
                if scenario == "build":
                    await ext.build_scene_async()
                elif scenario == "external_stage":
                    await omni.usd.get_context().new_stage_async()
                    assert not ext._scene_ready
                    await ext.build_scene_async()
                elif scenario == "extension_toggle":
                    manager = app.get_extension_manager()
                    ext_id = manager.get_enabled_extension_id("visiontwin.factory")
                    app_ext_id = manager.get_enabled_extension_id("visiontwin.app")
                    manager.set_extension_enabled_immediate(ext_id, False)
                    await updates(2)
                    assert old_runtime is not None and not old_runtime.alive
                    manager.set_extension_enabled_immediate(app_ext_id or "visiontwin.factory", True)
                    await updates(60)
                    ext = current()
                    assert ext is not None
                    await ext.build_scene_async()
                await spawn(ext, out / f"{scenario}_{repeat}_new")
                product = ext._sim.tracker.get(1)
                previous = product.prediction
                held[0][1]("injected old capture error")
                polluted = product.prediction != previous
                if not before:
                    assert not polluted, (scenario, repeat, product.prediction)
                    await old_runtime.tasks.drain()
                    assert not old_runtime.tasks.tasks and not old_runtime.tasks.errors
                else:
                    assert polluted, "before mode expected to reproduce the missing generation guard"
                rows.append(dict(scenario=scenario, repeat=repeat, stale_callback_applied=polluted,
                                 injection="callback held at frame-provider API boundary"))
                held.clear()
        if not before:
            for repeat in range(repeats):
                await spawn(ext, out / f"pending_{repeat}")
                provider = ext._frames
                provider._pool.delivery_delay_s = 1.0
                delivered = []
                provider.request_frame(lambda *args: delivered.append(True), lambda msg: delivered.append(True))
                await updates(1)
                assert provider.pending == 1
                ext.reset()
                await provider._pool.drain()
                assert provider.pending == 0 and not delivered and not provider._pool.owner.errors
                rows.append(dict(scenario="real_pending_reset", repeat=repeat, delivered_after_reset=False,
                                 pending=provider.pending, tasks=len(provider._pool.owner.tasks)))
            provider._pool.delivery_delay_s = 0
        report = dict(mode="before" if before else "after", repeats=repeats, rows=rows,
                      stale_callbacks_applied=sum(r.get("stale_callback_applied",False) for r in rows),
                      pass_expected_behavior=True)
        if before:
            report["source_snapshot"] = str(snapshot)
            ext.on_shutdown()
        (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[lifecycle] PASS: mode={report['mode']} scenarios={len(rows)} stale_applied={report['stale_callbacks_applied']}")
        code = 0
    except Exception:
        (out / "failure.json").write_text(json.dumps(dict(rows=rows, error=traceback.format_exc()), indent=2), encoding="utf-8")
        carb.log_error(traceback.format_exc())
    finally:
        app.post_quit(code)


asyncio.ensure_future(main())
