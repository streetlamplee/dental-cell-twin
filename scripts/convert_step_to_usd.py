"""Kit startup script (run with kit --exec): convert one STEP file to USD with the USD
converter (omni.kit.converter.hoops_core), then quit. Used by convert_step_to_usd.ps1.

Settings: --/visiontwin/cad/in=<stp>  --/visiontwin/cad/out=<usd>  --/visiontwin/cad/options=<json>
          --/visiontwin/cad/profile=<name in options "profiles">  (default "product")
          --/visiontwin/cad/tessLOD=<0..4>  optional override (LOD comparison)
Writes <usd>.convert.json next to the output: converter version, profile, the options the
converter actually received, source SHA256, duration and output size (provenance).
"""

import asyncio
import hashlib
import json
import os
import time
import traceback

import carb
import carb.settings
import omni.kit.app

TAG = "[convert_step]"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_options(opt_path, profile, lod):
    with open(opt_path, encoding="utf-8") as f:
        profiles = json.load(f)["profiles"]
    if profile not in profiles:
        raise KeyError(f"unknown profile {profile!r}, choose from {sorted(profiles)}")
    options = {k: v for k, v in profiles[profile].items() if not k.startswith("_")}
    if lod not in (None, ""):
        options["tessLOD"] = int(lod)
    # The converter's parseArgs() only accepts Dict[str, str].
    return {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in options.items()}


async def _main():
    app = omni.kit.app.get_app()
    s = carb.settings.get_settings()
    src, dst, opt_path = (s.get(f"/visiontwin/cad/{k}") for k in ("in", "out", "options"))
    profile = s.get("/visiontwin/cad/profile") or "product"
    code = 1
    try:
        options = _load_options(opt_path, profile, s.get("/visiontwin/cad/tessLOD"))
        mgr = app.get_extension_manager()
        if not mgr.set_extension_enabled_immediate("omni.kit.converter.hoops_core", True):
            raise RuntimeError("could not enable omni.kit.converter.hoops_core")
        ext_id = mgr.get_enabled_extension_id("omni.kit.converter.hoops_core")
        from omni.kit.converter.hoops_core import get_instance

        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isfile(dst):
            os.remove(dst)
        t0 = time.time()
        result = await get_instance().create_converter_task(src, dst, options)
        seconds = time.time() - t0
        status = result[1] if isinstance(result, tuple) and len(result) > 1 else None
        err = getattr(status, "error_code", 0) if status is not None else 0
        ok = os.path.isfile(dst) and not err
        print(f"{TAG} converter={ext_id} profile={profile} options={options}")
        print(f"{TAG} {os.path.basename(src)} -> {dst} ok={ok} ({seconds:.1f}s)"
              + (f" error={err} {getattr(status, 'error_msg', '')}" if err else ""))
        if ok:
            meta = {"converter": ext_id, "profile": profile, "options": options,
                    "source": os.path.basename(src), "source_sha256": _sha256(src),
                    "seconds": round(seconds, 2), "output_bytes": os.path.getsize(dst)}
            with open(dst + ".convert.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        code = 0 if ok else 2
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
