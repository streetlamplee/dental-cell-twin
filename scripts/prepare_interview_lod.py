"""Build fixed-count instanced scenes for LOD 0/3/4 using existing tessellation assets.

Usage: prepare_interview_lod.py. Outputs results/interview/lod/<timestamp>/manifest.json
and normalized USD fixtures. No new CAD conversion or CPU timing is performed here.
"""

from datetime import datetime
import json
import os
from pathlib import Path

from pxr import Gf, Usd, UsdGeom
from benchmark_usd_instancing import build

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / "results/interview/lod" / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    entries = []
    for lod in (0,3,4):
        raw = ROOT / f"results/cad_lod/dental_crown/lod{lod}.usd"
        assert raw.exists(), raw
        original = Usd.Stage.Open(str(raw))
        normalized = out / f"asset_lod{lod}.usda"
        stage = Usd.Stage.CreateNew(str(normalized))
        UsdGeom.SetStageMetersPerUnit(stage,1)
        UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
        root = UsdGeom.Xform.Define(stage,"/Part")
        stage.SetDefaultPrim(root.GetPrim())
        geometry = UsdGeom.Xform.Define(stage,"/Part/Geometry")
        geometry.GetPrim().GetReferences().AddReference(os.path.relpath(raw,out).replace("\\","/"))
        xf = UsdGeom.XformCommonAPI(root)
        xf.SetScale(Gf.Vec3f(UsdGeom.GetStageMetersPerUnit(original)))
        if UsdGeom.GetStageUpAxis(original) == UsdGeom.Tokens.y:
            xf.SetRotate(Gf.Vec3f(90,0,0))
        bounds = UsdGeom.BBoxCache(0,[UsdGeom.Tokens.default_]).ComputeWorldBound(root.GetPrim()).ComputeAlignedRange()
        lo, hi = bounds.GetMin(), bounds.GetMax()
        xf.SetTranslate(Gf.Vec3d(-(lo[0]+hi[0])/2,-(lo[1]+hi[1])/2,-lo[2]))
        stage.GetRootLayer().Save()
        path = out / f"instance_lod{lod}_50.usda"
        built = build(path,50,"instance",source=normalized)
        assert len(built.GetPrototypes()) > 0
        entries.append(dict(mode=f"instance_lod{lod}",count=50,scene=path.name,lod=lod,
                            source=str(raw.relative_to(ROOT))))
    (out / "manifest.json").write_text(json.dumps(dict(entries=entries, usd_version=Usd.GetVersion(),
        note="50 instanced crowns; only source tessellation changes; quality from existing CAD comparison"),indent=2),encoding="utf-8")
    (out / "quality_reference.md").write_text((ROOT / "results/cad_lod/dental_crown/table.md").read_text(encoding="utf-8"),encoding="utf-8")
    print(f"LOD fixtures: {out / 'manifest.json'}")


if __name__ == "__main__":
    main()
