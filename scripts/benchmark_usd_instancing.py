"""Build equivalent repeated CAD scenes and measure fresh-process USD opens.

Usage: benchmark_usd_instancing.py [--out directory]. Internal --worker opens one scene.
Outputs: USD fixtures, CPU samples, edit checks and manifest for the Kit render benchmark.
"""

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade
from _interview_metrics import process_memory

ROOT = Path(__file__).resolve().parents[1]


def worker(path):
    before = process_memory()
    t = time.perf_counter()
    stage = Usd.Stage.Open(str(path))
    elapsed = time.perf_counter() - t
    assert stage and stage.GetPrimAtPath("/World/P_0000/Part")
    cache = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
    box = cache.ComputeWorldBound(stage.GetPrimAtPath("/World/P_0000/Part")).ComputeAlignedRange()
    return dict(open_s=elapsed, before=before, after=process_memory(), usd_version=Usd.GetVersion(),
                prototype_count=len(stage.GetPrototypes()), instance_count=sum(p.IsInstance() for p in stage.Traverse()),
                bbox_min=list(box.GetMin()), bbox_max=list(box.GetMax()),
                prims=len(list(stage.Traverse())), expanded_prims=len(list(stage.Traverse(Usd.TraverseInstanceProxies()))))


def build(path, count, mode, source=None):
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageMetersPerUnit(stage, 1)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    source = source or ROOT / "assets/parts/usd/crown_good.usda"
    source_ref = os.path.relpath(source, path.parent).replace("\\", "/")
    width = math.ceil(math.sqrt(count))
    for i in range(count):
        base = f"/World/P_{i:04d}"
        UsdGeom.XformCommonAPI(UsdGeom.Xform.Define(stage, base)).SetTranslate(Gf.Vec3d((i % width)*0.025, (i // width)*0.025, 0))
        p = UsdGeom.Xform.Define(stage, base + "/Part").GetPrim()
        p.GetReferences().AddReference(source_ref)
        p.SetInstanceable(mode != "reference")
        if mode == "deinstanced":
            p.SetInstanceable(False)
    cam = UsdGeom.Camera.Define(stage, "/World/Camera")
    centre = Gf.Vec3d((width-1)*0.0125, (math.ceil(count/width)-1)*0.0125, 0)
    distance = max(0.15, width*0.04)
    view = Gf.Matrix4d().SetLookAt(centre + Gf.Vec3d(0, -distance, distance), centre, Gf.Vec3d(0,0,1))
    UsdGeom.Xformable(cam).AddTransformOp().Set(view.GetInverse())
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.001, 100))
    UsdLux.DomeLight.Define(stage, "/World/Light").CreateIntensityAttr(1000)
    stage.GetRootLayer().Save()
    return stage


def main(out):
    out.mkdir(parents=True, exist_ok=False)
    entries, cpu = [], []
    for count in (10, 50, 100):
        for mode in ("reference", "instance", "deinstanced"):
            path = out / f"{mode}_{count}.usda"
            stage = build(path, count, mode)
            if mode == "instance":
                assert len(stage.GetPrototypes()) > 0
            entries.append(dict(mode=mode, count=count, scene=path.name))
            del stage
            for repeat in range(3):
                proc = subprocess.run([sys.executable, __file__, "--worker", str(path)],
                                      capture_output=True, text=True, timeout=120, check=True)
                data = json.loads(proc.stdout)
                assert data["instance_count"] == (count if mode == "instance" else 0)
                cpu.append(dict(mode=mode, count=count, repeat=repeat, **data))
    for count in (10, 50, 100):
        rows = [r for r in cpu if r["count"] == count]
        assert all(r["bbox_min"] == rows[0]["bbox_min"] and r["bbox_max"] == rows[0]["bbox_max"] for r in rows)
    edit = build(out / "edit_check.usda", 2, "instance")
    mesh = next(p for p in edit.Traverse(Usd.TraverseInstanceProxies()) if p.IsA(UsdGeom.Mesh) and str(p.GetPath()).startswith("/World/P_0000"))
    mesh_path = str(mesh.GetPath())
    rejected = False
    try:
        UsdGeom.Mesh(mesh).CreateDisplayColorAttr([Gf.Vec3f(1,0,0)])
    except Exception as exc:
        rejected = True
        error = str(exc)
    assert rejected, "instance proxy edit should be rejected"
    edit.GetPrimAtPath("/World/P_0000/Part").SetInstanceable(False)
    UsdGeom.Mesh(edit.GetPrimAtPath(mesh_path)).CreateDisplayColorAttr([Gf.Vec3f(1,0,0)])
    material = UsdShade.Material.Define(edit, "/World/EditedMaterial")
    shader = UsdShade.Shader.Define(edit, "/World/EditedMaterial/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(1,0,0))
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(edit.GetPrimAtPath(mesh_path)).Bind(material)
    assert UsdShade.MaterialBindingAPI(edit.GetPrimAtPath(mesh_path)).ComputeBoundMaterial()[0].GetPath() == material.GetPath()
    assert not edit.GetPrimAtPath(mesh_path).IsInstanceProxy()
    assert edit.GetPrimAtPath("/World/P_0001/Part").IsInstance()
    edit.GetRootLayer().Save()
    report = dict(cpu=cpu, entries=entries, edit_check=dict(proxy_edit_rejected=rejected, error=error,
        selected_deinstanced=True, other_still_instance=True, selected_mesh_material_bound=True),
        environment=dict(cache="fresh worker process; OS filesystem cache uncontrolled", source="assets/parts/usd/crown_good.usda"))
    (out / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"PASS: {len(cpu)} process samples and independent-edit check; {out}")


if __name__ == "__main__":
    from datetime import datetime
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results/interview/instancing" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker)))
    else:
        main(args.out.resolve())
