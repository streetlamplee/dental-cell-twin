"""Kit startup script (run with kit --exec): convert one STEP file to USD with the USD
converter (omni.kit.converter.hoops_core), then quit. Used by convert_step_to_usd.ps1.

Settings: --/visiontwin/cad/in=<stp>  --/visiontwin/cad/out=<usd>  --/visiontwin/cad/options=<json>
"""

import asyncio
import json
import os
import time
import traceback

import carb
import carb.settings
import omni.kit.app

TAG = "[convert_step]"


async def _main():
    app = omni.kit.app.get_app()
    s = carb.settings.get_settings()
    src, dst, opt_path = (s.get(f"/visiontwin/cad/{k}") for k in ("in", "out", "options"))
    code = 1
    try:
        with open(opt_path, encoding="utf-8") as f:
            options = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
        mgr = app.get_extension_manager()
        if not mgr.set_extension_enabled_immediate("omni.kit.converter.hoops_core", True):
            raise RuntimeError("could not enable omni.kit.converter.hoops_core")
        ext_id = mgr.get_enabled_extension_id("omni.kit.converter.hoops_core")
        from omni.kit.converter.hoops_core import get_instance

        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isfile(dst):
            os.remove(dst)
        t0 = time.time()
        await get_instance().create_converter_task(src, dst, options)
        ok = os.path.isfile(dst)
        print(f"{TAG} converter={ext_id} options={options}")
        print(f"{TAG} {os.path.basename(src)} -> {dst} ok={ok} ({time.time() - t0:.1f}s)")
        code = 0 if ok else 2
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
