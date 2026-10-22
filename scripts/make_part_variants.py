"""Build product variant layers for a CAD part (run inside .venv-cad: usd-core).

For assets/parts/catalog.json entry <part>, writes assets/parts/usd/<part>_<variant>.usda:
  /Part (Xform: translate -> rotate -> scale)  references the converted USD (not edited)
    Looks/Paint                     UsdPreviewSurface with the variant's paint colour
    overrides: paint prims de-instanced, their meshes bound to Paint
               remove_insert: insert prims set inactive (missing-part defect)
Normalisation: rotation from the catalog, uniform scale so the longest side is
target_length_m (metres, stage metersPerUnit 1), centred in x/y, bottom at z = 0.

Usage: python scripts/make_part_variants.py <part>
"""

import json
import sys
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

PARTS = Path(__file__).resolve().parents[1] / "assets" / "parts"


def bounds(stage):
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    rng = cache.ComputeWorldBound(stage.GetPrimAtPath("/Part")).ComputeAlignedRange()
    return Gf.Vec3d(rng.GetMin()), Gf.Vec3d(rng.GetMax())


def make_paint(stage, rgb):
    mat = UsdShade.Material.Define(stage, "/Part/Looks/Paint")
    sh = UsdShade.Shader.Define(stage, "/Part/Looks/Paint/Surface")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.5)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def build(part: str, spec: dict, variant: str, vspec: dict) -> Path:
    src = PARTS / spec["converted_usd"]
    src_stage = Usd.Stage.Open(str(src))
    mpu = UsdGeom.GetStageMetersPerUnit(src_stage)
    out = PARTS / "usd" / f"{part}_{variant}.usda"

    stage = Usd.Stage.CreateNew(str(out)) if not out.exists() else Usd.Stage.Open(str(out))
    stage.GetRootLayer().Clear()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, "/Part")
    stage.SetDefaultPrim(root.GetPrim())
    root.GetPrim().GetReferences().AddReference(f"./{src.name}")
    root.GetPrim().SetCustomDataByKey("visiontwin", {
        "part": part, "variant": variant, "source_step": f"raw/{part}.step",
        "ground_truth": vspec["ground_truth"], "defect_kind": vspec["defect_kind"] or ""})

    xf = UsdGeom.XformCommonAPI(root)
    xf.SetRotate(Gf.Vec3f(*spec["rotate_xyz_deg"]), UsdGeom.XformCommonAPI.RotationOrderXYZ)
    xf.SetScale(Gf.Vec3f(mpu, mpu, mpu))
    lo, hi = bounds(stage)  # metres after rotation, before fitting
    size = max(hi - lo)
    k = spec["target_length_m"] / size
    xf.SetScale(Gf.Vec3f(mpu * k, mpu * k, mpu * k))
    lo, hi = bounds(stage)
    xf.SetTranslate(Gf.Vec3d(-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))

    paint = make_paint(stage, vspec["paint_rgb"])
    for rel in spec["paint_prims"]:
        prim = stage.GetPrimAtPath(f"/Part/{rel}")
        if not prim:
            raise RuntimeError(f"paint prim not found: {rel}")
        prim.SetInstanceable(False)  # instance proxies cannot carry overrides
        meshes = [p for p in Usd.PrimRange(prim) if p.IsA(UsdGeom.Mesh)]
        if not meshes:
            raise RuntimeError(f"no mesh under {rel}")
        for m in meshes:
            UsdShade.MaterialBindingAPI.Apply(m).Bind(paint)
    if vspec.get("remove_insert"):
        for rel in spec["insert_prims"]:
            prim = stage.GetPrimAtPath(f"/Part/{rel}")
            if not prim:
                raise RuntimeError(f"insert prim not found: {rel}")
            prim.SetActive(False)

    stage.GetRootLayer().Save()
    lo, hi = bounds(stage)
    dims = hi - lo
    print(f"{out.name}: size {dims[0]:.3f} x {dims[1]:.3f} x {dims[2]:.3f} m, scale x{k:.3f}, "
          f"gt={vspec['ground_truth']} kind={vspec['defect_kind']}")
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    part = sys.argv[1]
    catalog = json.loads((PARTS / "catalog.json").read_text(encoding="utf-8"))
    spec = catalog[part]
    for variant, vspec in spec["variants"].items():
        build(part, spec, variant, vspec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
