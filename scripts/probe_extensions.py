"""Kit startup script (run with kit --exec): which extensions does the registry offer for this
Kit version? Prints the newest compatible version (or "not found") for each name, then quits.
Read-only: nothing is enabled or downloaded. Used by scripts/probe_extensions.ps1.

Settings: --/visiontwin/probe/names=<comma separated extension names>
"""

import asyncio
import traceback

import carb
import carb.settings
import omni.kit.app

TAG = "[probe_ext]"


async def _main():
    app = omni.kit.app.get_app()
    code = 1
    try:
        names = [n.strip() for n in (carb.settings.get_settings().get("/visiontwin/probe/names") or "").split(",") if n.strip()]
        mgr = app.get_extension_manager()
        mgr.sync_registry()
        for _ in range(600):  # registry sync is asynchronous
            if mgr.get_registry_extensions():
                break
            await app.next_update_async()
        print(f"{TAG} kit {app.get_build_version()}, registry entries: {len(mgr.get_registry_extensions())}")
        for name in names:
            versions = mgr.fetch_extension_versions(name)
            local = mgr.get_enabled_extension_id(name) or ""
            if versions:
                newest = versions[0]
                print(f"{TAG} {name}: {len(versions)} version(s), newest {newest['id']}"
                      + (f" (enabled: {local})" if local else ""))
            else:
                print(f"{TAG} {name}: not found")
        code = 0
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
