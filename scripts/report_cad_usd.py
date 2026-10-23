"""Conversion quality report for a converted CAD USD (run inside .venv-cad: usd-core + OCP).

USD side (instance proxies included, units -> mm):
  meshes, triangles, points, meshes with normals / UVs, materials, HOOPS metadata attributes,
  world AABB size, mesh volume (divergence theorem, per mesh |signed volume|) and area.
STEP side (exact B-rep via OpenCascade, mm): volume, surface area, AABB size.
Errors: mesh vs B-rep volume and area in %, AABB size difference in mm. Tessellation
places vertices on the true surface, so the error shows how coarse the facets are.

Writes <usd>.report.json and prints one summary line. Exit 1 if the USD has no mesh.

Usage: python scripts/report_cad_usd.py <usd> <step>
"""

import json
import sys
from pathlib import Path

import numpy as np
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from pxr import Usd, UsdGeom, UsdShade


def brep_properties(step_path):
    reader = STEPControl_Reader()
    if reader.ReadFile(str(step_path)) != IFSelect_RetDone:
        raise RuntimeError(f"cannot read {step_path}")
    reader.TransferRoots()
    shape = reader.OneShape()
    vol, area = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vol)
    BRepGProp.SurfaceProperties_s(shape, area)
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)  # tight box from exact geometry (Add_s is loose)
    x0, y0, z0, x1, y1, z1 = box.Get()
    return {"volume_mm3": vol.Mass(), "area_mm2": area.Mass(), "size_mm": [x1 - x0, y1 - y0, z1 - z0]}


def mesh_properties(stage):
    to_mm = UsdGeom.GetStageMetersPerUnit(stage) * 1000.0
    out = {"meshes": 0, "triangles": 0, "points": 0, "with_normals": 0, "with_uvs": 0,
           "volume_mm3": 0.0, "area_mm2": 0.0}
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for prim in stage.Traverse(Usd.TraverseInstanceProxies()):
        if not prim.IsA(UsdGeom.Mesh) or UsdGeom.Imageable(prim).ComputeVisibility() == "invisible":
            continue
        mesh = UsdGeom.Mesh(prim)
        pts = np.array(mesh.GetPointsAttr().Get() or [], dtype=float)
        counts = np.array(mesh.GetFaceVertexCountsAttr().Get() or [], dtype=int)
        idx = np.array(mesh.GetFaceVertexIndicesAttr().Get() or [], dtype=int)
        if len(pts) == 0 or len(counts) == 0:
            continue
        m = np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
        world = (np.c_[pts, np.ones(len(pts))] @ m)[:, :3] * to_mm
        lo, hi = np.minimum(lo, world.min(0)), np.maximum(hi, world.max(0))
        tris, start = [], 0
        for c in counts:  # fan triangulation
            tris += [(idx[start], idx[start + k], idx[start + k + 1]) for k in range(1, c - 1)]
            start += c
        t = np.array(tris)
        a, b, c = world[t[:, 0]], world[t[:, 1]], world[t[:, 2]]
        out["volume_mm3"] += abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
        out["area_mm2"] += np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() / 2.0
        out["meshes"] += 1
        out["triangles"] += len(t)
        out["points"] += len(pts)
        out["with_normals"] += bool(mesh.GetNormalsAttr().Get() or prim.GetAttribute("primvars:normals").Get())
        out["with_uvs"] += bool(prim.GetAttribute("primvars:st").Get())
    out["size_mm"] = (hi - lo).tolist() if out["meshes"] else None
    return out


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    usd, step = Path(sys.argv[1]), Path(sys.argv[2])
    stage = Usd.Stage.Open(str(usd))
    usd_props = mesh_properties(stage)
    if not usd_props["meshes"]:
        print(f"FAIL {usd.name}: no mesh")
        return 1
    usd_props["materials"] = sum(1 for p in stage.Traverse() if p.IsA(UsdShade.Material))
    usd_props["metadata_attrs"] = sum(1 for p in stage.Traverse(Usd.TraverseInstanceProxies())
                                      for a in p.GetAttributes() if a.GetName().startswith("omni:hoops:metadata"))
    brep = brep_properties(step)
    convert = Path(str(usd) + ".convert.json")
    report = {
        "usd": usd.name, "step": step.name,
        "convert": json.loads(convert.read_text(encoding="utf-8")) if convert.exists() else None,
        "usd_mesh": usd_props, "step_brep": brep,
        "volume_error_pct": 100.0 * (usd_props["volume_mm3"] - brep["volume_mm3"]) / brep["volume_mm3"],
        "area_error_pct": 100.0 * (usd_props["area_mm2"] - brep["area_mm2"]) / brep["area_mm2"],
        "size_diff_mm": [u - b for u, b in zip(sorted(usd_props["size_mm"]), sorted(brep["size_mm"]))],
        "file_bytes": usd.stat().st_size,
    }
    Path(str(usd) + ".report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lod = (report["convert"] or {}).get("options", {}).get("tessLOD", "?")
    print(f"{usd.name}: LOD {lod}, meshes {usd_props['meshes']}, triangles {usd_props['triangles']}, "
          f"materials {usd_props['materials']}, metadata {usd_props['metadata_attrs']}, "
          f"volume err {report['volume_error_pct']:+.3f}%, area err {report['area_error_pct']:+.3f}%, "
          f"max size diff {max(abs(d) for d in report['size_diff_mm']):.3f} mm, {report['file_bytes'] / 1024:.0f} KiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
