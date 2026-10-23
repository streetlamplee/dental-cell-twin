"""Kit startup script (run with kit --exec): surface teaching evidence, then quit.
Used by scripts/render_teach_program.ps1.

Builds the crown line, opens the teach pendant (teach mode: URDF tool and block visible),
generates origin + 5 faces at the given standoff, and for every point poses the machine and
saves the teach close-up. (The spindle camera is not used here: in teach mode the URDF tool
sits right in front of it, 5-30 mm on its optical axis, and fills the frame.) Writes the exported program (JSON with
the verification of every point), report.md and a contact sheet. Also records whether a
closer standoff is reachable (the side faces run out of Z travel).

Settings: --/visiontwin/teach/out=<dir>  --/visiontwin/teach/standoffMm=20  --/visiontwin/teach/closeMm=10
"""

import asyncio
import json
import os
import traceback

import carb
import carb.settings
import cv2
import numpy as np
import omni.kit.app
from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport, next_viewport_frame_async

TAG = "[teach]"


async def _wait_for(get, app, frames=3000):
    for _ in range(frames):
        v = get()
        if v:
            return v
        await app.next_update_async()
    raise TimeoutError("startup")


async def _capture(vp, cam, path):
    vp.camera_path = cam
    await next_viewport_frame_async(vp, 20)
    return bool(await capture_viewport_to_file(vp, path).wait_for_result(completion_frames=60))


async def _main():
    app = omni.kit.app.get_app()
    s = carb.settings.get_settings()
    out = s.get("/visiontwin/teach/out")
    standoff = float(s.get("/visiontwin/teach/standoffMm") or 20.0) / 1000.0
    close = float(s.get("/visiontwin/teach/closeMm") or 10.0) / 1000.0
    code = 1
    try:
        import visiontwin.factory.extension as vt
        from visiontwin.factory.core import layout as L

        ext = await _wait_for(vt.get_instance, app)
        vp = await _wait_for(get_active_viewport, app)
        s.set("/exts/visiontwin.factory/part", "crown")
        await ext.build_scene_async()
        pendant = ext.open_teach_pendant()
        teacher = pendant.teacher
        try:
            teacher.face_program(close)
            close_result = f"{close * 1000:.0f} mm: all faces reachable"
        except ValueError as exc:
            close_result = str(exc)
        pendant.points = teacher.face_program(standoff)
        os.makedirs(out, exist_ok=True)
        rows, tiles = [], []
        for i, p in enumerate(pendant.points):
            pendant.set_pose(p.q)
            await next_viewport_frame_async(vp, 10)
            close_png = os.path.join(out, f"{i}_{p.name}_closeup.png")
            ok = await _capture(vp, L.TEACH_CAMERA_PATH, close_png)
            c = teacher.verify(p.q, p.face) if p.face else None
            rows.append({"point": p.name, **{k: round(v * (1000 if k[0] in "xyz" else 57.29577951308232), 2)
                                              for k, v in p.q.items()},
                         "angle_deg": round(c.angle_deg, 4) if c else "", "offset_mm": round(c.offset_mm, 4) if c else "",
                         "standoff_mm": round(c.standoff_mm, 2) if c else "", "limits": c.within_limits if c else True,
                         "captured": ok})
            img = cv2.imread(close_png)
            if img is not None:
                img = cv2.resize(img, (480, int(img.shape[0] * 480 / img.shape[1])))
                cv2.rectangle(img, (0, 0), (479, 26), (20, 20, 22), -1)
                cv2.putText(img, f"{i}. {p.name}", (8, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (240, 240, 240), 1)
                tiles.append(img)
            print(f"{TAG} {p.name}: {rows[-1]}")
        pendant.export_dir = out
        program_path = pendant.export()
        if tiles:
            h = max(t.shape[0] for t in tiles)
            tiles = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(252, 252, 251)) for t in tiles]
            rows_img = [np.hstack(tiles[k:k + 3] + [np.full_like(tiles[0], 252)] * (3 - len(tiles[k:k + 3])))
                        for k in range(0, len(tiles), 3)]
            cv2.imwrite(os.path.join(out, "contact_sheet.png"), np.vstack(rows_img))
        cols = ["point", "x_joint", "y_joint", "z_joint", "b_joint", "c_joint", "angle_deg", "offset_mm", "standoff_mm", "limits"]
        lines = [f"# Surface teaching: origin + 5 faces, standoff {standoff * 1000:.0f} mm", "",
                 "X/Y/Z in mm, B/C in deg; angle = tool axis vs face normal; offset = tool tip from the face centre line.", "",
                 "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
        lines += ["", f"Closer standoff: {close_result}", "", f"Program: {os.path.basename(program_path)}"]
        with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
            json.dump({"standoff_mm": standoff * 1000, "rows": rows, "closer_standoff": close_result}, f, indent=2)
        pendant.destroy()
        print(f"{TAG} done -> {out}")
        code = 0 if all(r["captured"] for r in rows) else 2
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
