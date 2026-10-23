"""Kit startup script (run with kit --exec): synthetic training data for the inspection cell with
Omniverse Replicator. Used by scripts/generate_dataset.ps1.

The scene is the real line (extension build: conveyor, inspection cell, spindle camera, robot);
for every sample one crown variant sits on the platter pad and the machine is posed at each of
the cell's views; Replicator renders the spindle camera and its BasicWriter saves the frames.

Domain randomisation per product sample (seeded, recorded in labels.csv):
  variant      good / color / shape / chip (weights 0.5 / 0.5/3 each)
  lighting     key + dome intensity factor, log-uniform in [light_min, light_max]; key light
               direction +-15 deg
  shade        good ivory and defect pink colours jittered per channel
  placement    yaw 0..360 deg (a chip can face any side), +-1.5 mm on the pad
  camera       +-1 mm x/y, +-3 mm z per view
Labels come from the generator (ground truth), never from the images.

Settings: --/visiontwin/sdg/out=<dir> --/visiontwin/sdg/samples=<n> --/visiontwin/sdg/seed=<s>
          --/visiontwin/sdg/lightMin=0.3 --/visiontwin/sdg/lightMax=1.6
"""

import asyncio
import csv
import glob
import json
import math
import os
import traceback

import carb
import carb.settings
import numpy as np
import omni.kit.app
import omni.usd
from omni.kit.viewport.utility import get_active_viewport
from pxr import Gf, UsdGeom

TAG = "[sdg]"
VARIANTS = (("good", None), ("defect", "color"), ("defect", "shape"), ("defect", "chip"))
WEIGHTS = (0.5, 0.5 / 3, 0.5 / 3, 0.5 / 3)
BASE_SHADE = {None: (0.93, 0.90, 0.80), "color": (0.92, 0.55, 0.62), "shape": (0.93, 0.90, 0.80),
              "chip": (0.93, 0.90, 0.80)}


async def _wait_for(get, app, frames=3000):
    for _ in range(frames):
        v = get()
        if v:
            return v
        await app.next_update_async()
    raise TimeoutError("startup")


def _rz(deg, dx=0.0, dy=0.0):
    m = np.eye(4)
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    m[:3, :3] = [[c, -s, 0], [s, c, 0], [0, 0, 1]]
    m[:3, 3] = (dx, dy, 0.0)
    return m


async def _main():
    app = omni.kit.app.get_app()
    s = carb.settings.get_settings()
    out = s.get("/visiontwin/sdg/out")
    n = int(s.get("/visiontwin/sdg/samples") or 10)
    seed = int(s.get("/visiontwin/sdg/seed") or 0)
    lmin, lmax = float(s.get("/visiontwin/sdg/lightMin") or 0.3), float(s.get("/visiontwin/sdg/lightMax") or 1.6)
    code = 1
    try:
        import visiontwin.factory.extension as vt
        from visiontwin.factory import scene_manager as scene
        from visiontwin.factory.core import layout as L
        from visiontwin.factory.core.camera_model import inspection_roi

        ext = await _wait_for(vt.get_instance, app)
        await _wait_for(get_active_viewport, app)
        s.set("/exts/visiontwin.factory/part", "crown")
        await ext.build_scene_async()
        stage = omni.usd.get_context().get_stage()
        cell, cat = ext._cell, ext._catalog
        cycle = cell.cycle
        views = [v.name for v in cycle.views]

        pids = {}
        for i, (gt, kind) in enumerate(VARIANTS):
            pid = 9001 + i
            scene.spawn_product_prim(stage, pid, kind, 0.0, cat.variant_path(gt, kind), None)
            pids[(gt, kind)] = pid
        key = stage.GetPrimAtPath(f"{L.FACTORY_PATH}/KeyLight")
        dome = stage.GetPrimAtPath(f"{L.FACTORY_PATH}/Ambient")
        key_i, dome_i = key.GetAttribute("inputs:intensity").Get(), dome.GetAttribute("inputs:intensity").Get()

        mgr = app.get_extension_manager()
        mgr.set_extension_enabled_immediate("omni.replicator.core", True)
        import omni.replicator.core as rep

        rp = rep.create.render_product(L.CELL_CAMERA_PATH, L.CAMERA_RESOLUTION)
        img_dir = os.path.join(out, "replicator")
        writer = rep.WriterRegistry.get("BasicWriter")
        writer.initialize(output_dir=img_dir, rgb=True)
        writer.attach([rp])

        rng = np.random.default_rng(seed)
        rows = []
        for i in range(n):
            gt, kind = VARIANTS[int(rng.choice(len(VARIANTS), p=WEIGHTS))]
            pid = pids[(gt, kind)]
            for other in pids.values():
                prim = stage.GetPrimAtPath(scene.product_path(other))
                (UsdGeom.Imageable(prim).MakeVisible if other == pid else UsdGeom.Imageable(prim).MakeInvisible)()
            light = float(math.exp(rng.uniform(math.log(lmin), math.log(lmax))))
            key.GetAttribute("inputs:intensity").Set(key_i * light)
            dome.GetAttribute("inputs:intensity").Set(dome_i * light)
            UsdGeom.XformCommonAPI(key).SetRotate(Gf.Vec3f(-30.0 + rng.uniform(-15, 15), 20.0 + rng.uniform(-15, 15), 0.0))
            shade = np.clip(np.array(BASE_SHADE[kind]) + rng.uniform(-0.03, 0.03, 3), 0, 1)
            paint = stage.GetPrimAtPath(f"{scene.product_path(pid)}/Pose/Part/Looks/Paint/Surface")
            paint.GetAttribute("inputs:diffuseColor").Set(Gf.Vec3f(*shade))
            yaw, dx, dy = rng.uniform(0, 360), rng.uniform(-0.0015, 0.0015), rng.uniform(-0.0015, 0.0015)
            for k, vt_k in enumerate(cycle.view_times):
                cam = (rng.uniform(-0.001, 0.001), rng.uniform(-0.001, 0.001), rng.uniform(-0.003, 0.003))
                cell.apply(vt_k, camera_offset=cam)
                scene.set_product_pose(stage, pid, cell.seat_pose() @ _rz(yaw, dx, dy))
                await rep.orchestrator.step_async(rt_subframes=2)
                rows.append({"sample": i, "view": k, "view_name": views[k], "ground_truth": gt,
                             "defect_kind": kind or "", "light": round(light, 4), "yaw_deg": round(yaw, 2),
                             "shade": " ".join(f"{c:.3f}" for c in shade)})
            if i % 50 == 0:
                print(f"{TAG} sample {i}/{n}")
        await rep.orchestrator.wait_until_complete_async()
        writer.detach()
        files = sorted(glob.glob(os.path.join(img_dir, "**", "rgb_*.png"), recursive=True))
        if len(files) != len(rows):
            raise RuntimeError(f"{len(files)} images for {len(rows)} labels")
        for row, f in zip(rows, files):
            row["file"] = os.path.relpath(f, out).replace("\\", "/")
        with open(os.path.join(out, "labels.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        spec = cat.cell
        roi = inspection_roi(L.CAMERA_RESOLUTION, spec.focal_mm, L.CAMERA_H_APERTURE_MM, spec.standoff_m,
                             spec.roi_half_m, spec.roi_half_m)
        meta = {"samples": n, "seed": seed, "views": views, "images": len(rows), "light_range": [lmin, lmax],
                "variants": [f"{g}:{k or '-'}" for g, k in VARIANTS], "weights": WEIGHTS, "roi": list(roi),
                "resolution": list(L.CAMERA_RESOLUTION), "replicator": mgr.get_enabled_extension_id("omni.replicator.core")}
        with open(os.path.join(out, "dataset.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        print(f"{TAG} done: {n} samples, {len(rows)} images -> {out}")
        code = 0
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
