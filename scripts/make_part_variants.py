"""Build product variant layers for a CAD part (run inside .venv-cad: usd-core).

For assets/parts/catalog.json entry <part>, writes for every variant:
  usd/<part>_<variant>.usda        final shape (what leaves the line)
  usd/<part>_<variant>_raw.usda    shape before processing (only if the variant has "raw")
Each layer: /Part (Xform: translate -> rotate -> scale) referencing a converted USD
(never edited), Looks/Paint (UsdPreviewSurface) bound to the paint prims ("*" = every
mesh), optional insert prims deactivated (missing-part defect).
Normalisation: rotation from the catalog; scale = target_length_m / longest side if given,
else the part keeps its real size (metres); centred in x/y, bottom at z = 0.

A variant either uses the part-level "converted_usd" (or its own "source") + its own
paint/remove settings (single stage, e.g. kfl08, crown), or defines "raw"/"final" stages with their own "source" and
"paint_rgb" (processed parts, e.g. the dental crown).

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


def paint_targets(stage, rels):
    if rels == ["*"]:
        # De-instance every instanceable prim so its meshes can carry a binding override.
        # Collect first, then edit (editing invalidates proxies); repeat for nested instances.
        while True:
            found = [p.GetPath() for p in Usd.PrimRange(stage.GetPrimAtPath("/Part")) if p.IsInstanceable()]
            if not found:
                break
            for path in found:
                stage.GetPrimAtPath(path).SetInstanceable(False)
        return [p for p in Usd.PrimRange(stage.GetPrimAtPath("/Part")) if p.IsA(UsdGeom.Mesh)]
    meshes = []
    for rel in rels:
        prim = stage.GetPrimAtPath(f"/Part/{rel}")
        if not prim:
            raise RuntimeError(f"paint prim not found: {rel}")
        prim.SetInstanceable(False)  # instance proxies cannot carry overrides
        found = [p for p in Usd.PrimRange(prim) if p.IsA(UsdGeom.Mesh)]
        if not found:
            raise RuntimeError(f"no mesh under {rel}")
        meshes += found
    return meshes


def build_layer(out: Path, source: Path, spec: dict, paint_rgb, remove_insert: bool, meta: dict) -> None:
    mpu = UsdGeom.GetStageMetersPerUnit(Usd.Stage.Open(str(source)))
    stage = Usd.Stage.CreateNew(str(out)) if not out.exists() else Usd.Stage.Open(str(out))
    stage.GetRootLayer().Clear()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, "/Part")
    stage.SetDefaultPrim(root.GetPrim())
    root.GetPrim().GetReferences().AddReference(f"./{source.name}")
    root.GetPrim().SetCustomDataByKey("visiontwin", meta)

    xf = UsdGeom.XformCommonAPI(root)
    xf.SetRotate(Gf.Vec3f(*spec.get("rotate_xyz_deg", [0, 0, 0])), UsdGeom.XformCommonAPI.RotationOrderXYZ)
    xf.SetScale(Gf.Vec3f(mpu, mpu, mpu))
    k = 1.0
    if spec.get("target_length_m"):
        lo, hi = bounds(stage)
        k = spec["target_length_m"] / max(hi - lo)
        xf.SetScale(Gf.Vec3f(mpu * k, mpu * k, mpu * k))
    lo, hi = bounds(stage)
    xf.SetTranslate(Gf.Vec3d(-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))

    paint = make_paint(stage, paint_rgb)
    for m in paint_targets(stage, spec["paint_prims"]):
        UsdShade.MaterialBindingAPI.Apply(m).Bind(paint)
    if remove_insert:
        for rel in spec["insert_prims"]:
            prim = stage.GetPrimAtPath(f"/Part/{rel}")
            if not prim:
                raise RuntimeError(f"insert prim not found: {rel}")
            prim.SetActive(False)

    stage.GetRootLayer().Save()
    lo, hi = bounds(stage)
    d = hi - lo
    print(f"{out.name}: {d[0] * 1000:.1f} x {d[1] * 1000:.1f} x {d[2] * 1000:.1f} mm, scale x{k:.3f}, "
          f"src={source.name}, gt={meta['ground_truth']} kind={meta['defect_kind'] or '-'}")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    part = sys.argv[1]
    spec = json.loads((PARTS / "catalog.json").read_text(encoding="utf-8"))[part]
    for variant, v in spec["variants"].items():
        meta = {"part": part, "variant": variant, "ground_truth": v["ground_truth"],
                "defect_kind": v["defect_kind"] or ""}
        if "final" in v:  # processed part: raw + final stages
            for stage_name, suffix in (("raw", "_raw"), ("final", "")):
                st = v[stage_name]
                build_layer(PARTS / "usd" / f"{part}_{variant}{suffix}.usda", PARTS / st["source"], spec,
                            st["paint_rgb"], st.get("remove_insert", False), {**meta, "stage": stage_name})
        else:
            source = PARTS / v.get("source", spec.get("converted_usd", ""))  # per-variant shape (e.g. crown defects)
            build_layer(PARTS / "usd" / f"{part}_{variant}.usda", source, spec,
                        v["paint_rgb"], v.get("remove_insert", False), {**meta, "stage": "final"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
