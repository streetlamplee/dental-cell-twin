"""Create and assert small USD composition examples; run with the CAD Python environment.

Usage: verify_usd_composition.py [--out directory]
Outputs: independent USD layers, report.json and report.md; nonzero exit on failed assertions.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom

ROOT = Path(__file__).resolve().parents[1]


def new(path, root="/Part", unit=1.0):
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageMetersPerUnit(stage, unit)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    prim = UsdGeom.Xform.Define(stage, root).GetPrim()
    stage.SetDefaultPrim(prim)
    return stage, prim


def pos(stage, path):
    return list(UsdGeom.Xformable(stage.GetPrimAtPath(path)).ComputeLocalToWorldTransform(0).ExtractTranslation())


def bounds(stage, path):
    box = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_]).ComputeWorldBound(stage.GetPrimAtPath(path)).ComputeAlignedRange()
    return dict(min=list(box.GetMin()), max=list(box.GetMax()))


def close(actual, expected):
    assert len(actual) == len(expected) and all(math.isclose(a, b, abs_tol=1e-7) for a, b in zip(actual, expected)), (actual, expected)


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    asset_path = out / "asset.usda"
    asset, prim = new(asset_path)
    UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(-0.1, 0, 0.02))
    UsdGeom.Cube.Define(asset, "/Part/Cube").CreateSizeAttr(0.1)
    asset.GetRootLayer().Save()
    original = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    result = dict(usd_version=Usd.GetVersion(), checks={})

    same, p = new(out / "same_prim.usda")
    p.GetReferences().AddReference("./asset.usda")
    UsdGeom.XformCommonAPI(p).SetTranslate(Gf.Vec3d(10, 0, 0))
    same.GetRootLayer().Save()
    wrapped, parent = new(out / "parent_xform.usda", "/World")
    UsdGeom.XformCommonAPI(parent).SetTranslate(Gf.Vec3d(10, 0, 0))
    UsdGeom.Xform.Define(wrapped, "/World/Part").GetPrim().GetReferences().AddReference("./asset.usda")
    wrapped.GetRootLayer().Save()
    close(pos(same, "/Part"), [10, 0, 0])
    close(pos(wrapped, "/World/Part"), [9.9, 0, 0.02])
    result["checks"]["transform_collision"] = dict(same_prim=pos(same, "/Part"),
        wrapped=pos(wrapped, "/World/Part"), same_bbox=bounds(same, "/Part"), wrapped_bbox=bounds(wrapped, "/World/Part"),
        same_ops=[x.GetOpName() for x in UsdGeom.Xformable(same.GetDefaultPrim()).GetOrderedXformOps()])

    layout, parent = new(out / "layout.usda", "/World")
    UsdGeom.XformCommonAPI(parent).SetTranslate(Gf.Vec3d(2, 0, 0))
    UsdGeom.Xform.Define(layout, "/World/Part").GetPrim().GetReferences().AddReference("./asset.usda")
    layout.GetRootLayer().Save()
    runtime = Sdf.Layer.CreateNew(str(out / "runtime.usda"))
    root, _ = new(out / "composed.usda", "/World")
    root.GetRootLayer().subLayerPaths = ["./runtime.usda", "./layout.usda"]
    with Usd.EditContext(root, runtime):
        UsdGeom.XformCommonAPI(root.GetPrimAtPath("/World")).SetTranslate(Gf.Vec3d(3, 0, 0))
    runtime.Save()
    root.GetRootLayer().Save()
    attr = root.GetPrimAtPath("/World").GetAttribute("xformOp:translate")
    stack = [dict(layer=Path(s.layer.realPath).name, path=str(s.path), value=str(s.default)) for s in attr.GetPropertyStack()]
    close(pos(root, "/World/Part"), [2.9, 0, 0.02])
    # Remove only the runtime opinion, preserving layout and source geometry.
    runtime.Clear()
    runtime.Save()
    close(pos(root, "/World/Part"), [1.9, 0, 0.02])
    reopened = Usd.Stage.Open(str(out / "composed.usda"))
    close(pos(reopened, "/World/Part"), [1.9, 0, 0.02])
    result["checks"]["layer_reset"] = dict(strong_to_weak=stack, after_reset=pos(reopened, "/World/Part"))

    for name, rgb in (("good", (0.8, 0.8, 0.8)), ("red", (1, 0, 0))):
        derived, p = new(out / f"derived_{name}.usda")
        p.GetReferences().AddReference("./asset.usda")
        UsdGeom.Cube(derived.GetPrimAtPath("/Part/Cube")).CreateDisplayColorAttr([Gf.Vec3f(*rgb)])
        derived.GetRootLayer().Save()
    variants, p = new(out / "variants.usda")
    p.GetReferences().AddReference("./asset.usda")
    variant_set = p.GetVariantSets().AddVariantSet("finish")
    for name, rgb in (("good", (0.8, 0.8, 0.8)), ("red", (1, 0, 0))):
        variant_set.AddVariant(name)
        variant_set.SetVariantSelection(name)
        with variant_set.GetVariantEditContext():
            UsdGeom.Cube(variants.GetPrimAtPath("/Part/Cube")).CreateDisplayColorAttr([Gf.Vec3f(*rgb)])
        derived_check = Usd.Stage.Open(str(out / f"derived_{name}.usda"))
        expected = UsdGeom.Cube(derived_check.GetPrimAtPath("/Part/Cube")).GetDisplayColorAttr().Get()[0]
        close(UsdGeom.Cube(variants.GetPrimAtPath("/Part/Cube")).GetDisplayColorAttr().Get()[0], expected)
    variant_set.SetVariantSelection("red")
    variants.GetRootLayer().Save()
    reread = Usd.Stage.Open(str(out / "variants.usda"))
    assert reread.GetDefaultPrim().GetVariantSet("finish").GetVariantSelection() == "red"
    result["checks"]["variants"] = dict(selection="red", source_shared=True,
        decision="keep existing derived files for catalog compatibility; VariantSet is a verified alternative")

    millimeters, p = new(out / "millimeters.usda", unit=0.001)
    UsdGeom.Cube.Define(millimeters, "/Part/Cube").CreateSizeAttr(1000)
    millimeters.GetRootLayer().Save()
    meters, p = new(out / "meters.usda")
    p.GetReferences().AddReference("./millimeters.usda")
    unscaled = bounds(meters, "/Part")
    UsdGeom.XformCommonAPI(p).SetScale(Gf.Vec3f(0.001))
    normalized = bounds(meters, "/Part")
    close([b-a for a,b in zip(normalized["min"], normalized["max"])], [1, 1, 1])
    meters.GetRootLayer().Save()
    axis = Usd.Stage.CreateInMemory()
    marker = UsdGeom.Xform.Define(axis, "/Marker")
    UsdGeom.XformCommonAPI(marker).SetTranslate(Gf.Vec3d(0, 1, 0))
    UsdGeom.SetStageUpAxis(axis, UsdGeom.Tokens.y)
    UsdGeom.SetStageUpAxis(axis, UsdGeom.Tokens.z)
    close(pos(axis, "/Marker"), [0, 1, 0])
    converted = Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(1, 0, 0), 90)).TransformDir(Gf.Vec3d(0, 1, 0))
    close(converted, [0, 0, 1])
    result["checks"]["units_and_axes"] = dict(unscaled_bbox=unscaled, meters_bbox=normalized,
        metadata_only=pos(axis, "/Marker"), explicit_axis_conversion=list(converted))
    assert hashlib.sha256(asset_path.read_bytes()).hexdigest() == original
    result["checks"]["source_hash_unchanged"] = original
    (out / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (out / "report.md").write_text("# USD composition verification\n\n" +
        "\n".join(f"- PASS: {k}" for k in result["checks"]) +
        "\n\nSee report.json and the independent USD files for values and property stacks.\n", encoding="utf-8")
    print(f"PASS: {len(result['checks'])} composition checks; {out}")


if __name__ == "__main__":
    from datetime import datetime
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results/interview/composition" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    run(parser.parse_args().out.resolve())
