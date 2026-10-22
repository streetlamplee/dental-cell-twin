"""Kit startup script (run with kit --exec): Gate C probe for the USD converter.

Enables omni.kit.converter.hoops_core (pulled from the registry if needed), converts one
STP file with the same options as the user's usd_converter project, then prints the
resulting stage's units, up axis, prim tree (first levels) and world bounds. Quits after.

Settings: --/visiontwin/cad/in=<stp path>  --/visiontwin/cad/out=<usd path>
"""

import asyncio
import os
import time
import traceback

import carb
import carb.settings
import omni.kit.app

TAG = "[probe_cad]"

# Options copied from usd_converter (my_company.stp_pipeline_setup/converter.py)
CONVERT_OPTIONS = {
    "bOptimize": "true",
    "instancing": "true",
    "tessLOD": "0",
    "convertMetadata": "false",
    "useMaterials": "false",
}


async def _main():
    app = omni.kit.app.get_app()
    s = carb.settings.get_settings()
    src, dst = s.get("/visiontwin/cad/in"), s.get("/visiontwin/cad/out")
    code = 1
    try:
        mgr = app.get_extension_manager()
        ok = mgr.set_extension_enabled_immediate("omni.kit.converter.hoops_core", True)
        print(f"{TAG} enable hoops_core: {ok}")
        for ext in mgr.get_extensions():
            if "converter" in ext["name"] and ext.get("enabled"):
                print(f"{TAG} enabled: {ext['id']}")
        from omni.kit.converter.hoops_core import get_instance

        os.makedirs(os.path.dirname(dst), exist_ok=True)
        t0 = time.time()
        await get_instance().create_converter_task(src, dst, dict(CONVERT_OPTIONS))
        print(f"{TAG} convert {os.path.basename(src)} -> exists={os.path.isfile(dst)} in {time.time() - t0:.1f}s")
        if os.path.isfile(dst):
            from pxr import Usd, UsdGeom

            stage = Usd.Stage.Open(dst)
            print(f"{TAG} metersPerUnit={UsdGeom.GetStageMetersPerUnit(stage)} upAxis={UsdGeom.GetStageUpAxis(stage)}")
            for prim in stage.Traverse():
                depth = str(prim.GetPath()).count("/")
                if depth <= 5:
                    print(f"{TAG} prim {prim.GetPath()} [{prim.GetTypeName()}]")
            cache = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
            print(f"{TAG} world bounds: {cache.ComputeWorldBound(stage.GetPseudoRoot()).ComputeAlignedRange()}")
            code = 0
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
