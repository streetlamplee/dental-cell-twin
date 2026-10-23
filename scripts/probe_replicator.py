"""Kit startup script (run with kit --exec): enable omni.replicator.core (downloads it from the
registry the first time) and print the API this project uses, then quit.
Used by scripts/probe_replicator.ps1.
"""

import asyncio
import inspect
import traceback

import carb
import omni.kit.app

TAG = "[probe_rep]"


async def _main():
    app = omni.kit.app.get_app()
    code = 1
    try:
        mgr = app.get_extension_manager()
        ok = mgr.set_extension_enabled_immediate("omni.replicator.core", True)
        print(f"{TAG} enabled={ok} id={mgr.get_enabled_extension_id('omni.replicator.core')}")
        import omni.replicator.core as rep

        for name, fn in (("create.render_product", rep.create.render_product),
                         ("orchestrator.step_async", rep.orchestrator.step_async),
                         ("BasicWriter.initialize", rep.WriterRegistry.get("BasicWriter").initialize)):
            print(f"{TAG} {name}{inspect.signature(fn)}")
        print(f"{TAG} writers: {sorted(rep.WriterRegistry.get_writers().keys())[:20]}")
        code = 0
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
