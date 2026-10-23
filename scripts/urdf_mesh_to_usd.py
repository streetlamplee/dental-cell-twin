"""URDF with mesh (STL) visuals -> USD + kinematics.json (run inside .venv-cad: usd-core + numpy).

USD layout matches the CAD mill asset, so the same forward-kinematics driver works:
  /<robot>                 defaultPrim, metres, Z up
    /Looks/<material>      UsdPreviewSurface per URDF material colour
    /<link>                Xform at the home-pose (all joints 0) transform
      /<visual>            Xform at the visual origin, with Mesh child (triangles from the STL)
kinematics.json (next to the USD): joints from the URDF (core.urdf_model.kinematics()) plus
the visual list, the source of truth for joint motion.

Usage: python scripts/urdf_mesh_to_usd.py <urdf> <out.usd>
"""

import json
import re
import struct
import sys
from pathlib import Path

import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, Vt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/extensions/visiontwin.factory/visiontwin/factory"))

from core.urdf_model import load_urdf  # noqa: E402


def read_stl(path: Path) -> np.ndarray:
    """Triangles (N, 3, 3) from a binary or ASCII STL."""
    data = path.read_bytes()
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if 84 + 50 * n == len(data):  # binary
            rec = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]),
                                count=n, offset=84)
            return rec["v"].astype(np.float64)
    nums = re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", data)
    return np.array(nums, dtype=np.float64).reshape(-1, 3, 3)


def ident(name: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return out if out and not out[0].isdigit() else f"_{out}"


def gf(m: np.ndarray) -> Gf.Matrix4d:
    return Gf.Matrix4d(np.asarray(m, dtype=float).T.tolist())  # USD: row vectors


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    urdf, out = Path(sys.argv[1]), Path(sys.argv[2])
    model = load_urdf(str(urdf))
    home = model.link_transforms()
    stage = Usd.Stage.CreateNew(str(out)) if not out.exists() else Usd.Stage.Open(str(out))
    stage.GetRootLayer().Clear()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    robot_path = f"/{ident(model.name)}"
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, robot_path).GetPrim())

    looks = {}
    def material(name, rgba):
        key = name or f"rgba_{'_'.join(f'{c:.3f}' for c in rgba)}"
        if key not in looks:
            mat = UsdShade.Material.Define(stage, f"{robot_path}/Looks/{ident(key)}")
            sh = UsdShade.Shader.Define(stage, f"{mat.GetPath()}/Surface")
            sh.CreateIdAttr("UsdPreviewSurface")
            sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgba[:3]))
            sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.45)
            mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
            looks[key] = mat
        return looks[key]

    tris_total, mapping = 0, []
    for link in model.links.values():
        lx = UsdGeom.Xform.Define(stage, f"{robot_path}/{ident(link.name)}")
        lx.AddTransformOp().Set(gf(home[link.name]))
        for v in link.visuals:
            if v.shape != "mesh":
                raise ValueError(f"{link.name}/{v.name}: only mesh visuals here (box/cylinder: urdf_to_step)")
            tris = read_stl((urdf.parent / v.mesh).resolve()) * np.array(v.size)
            vx = UsdGeom.Xform.Define(stage, f"{lx.GetPath()}/{ident(v.name)}")
            vx.AddTransformOp().Set(gf(v.origin))
            mesh = UsdGeom.Mesh.Define(stage, f"{vx.GetPath()}/Mesh")
            pts = tris.reshape(-1, 3)
            mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(pts.astype(np.float32)))
            mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(tris), 3, np.int32)))
            mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(np.arange(len(pts), dtype=np.int32)))
            mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
            mesh.CreateDisplayColorAttr([Gf.Vec3f(*v.rgba[:3])])
            mesh.CreateExtentAttr([Gf.Vec3f(*pts.min(0)), Gf.Vec3f(*pts.max(0))])
            UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material(v.material, v.rgba))
            tris_total += len(tris)
            mapping.append({"link": link.name, "visual": v.name, "part": ident(v.name), "mesh": v.mesh,
                            "rgba": list(v.rgba)})
    stage.GetRootLayer().Save()

    kin = model.kinematics()
    kin["source"] = urdf.name
    kin["usd"] = {"file": out.name, "length_unit": "m", "pose": "home (all joint values 0)",
                  "hierarchy": f"{ident(model.name)}/<link>/<visual>/Mesh"}
    kin["visuals"] = mapping
    kin_path = out.with_suffix(".kinematics.json")
    kin_path.write_text(json.dumps(kin, indent=2), encoding="utf-8")
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    rng = cache.ComputeWorldBound(stage.GetPrimAtPath(robot_path)).ComputeAlignedRange()
    size = rng.GetMax() - rng.GetMin()
    print(f"{out.name}: links {len(model.links)}, joints {len(model.joints)}, visuals {len(mapping)}, "
          f"triangles {tris_total}, materials {len(looks)}, home bbox {size[0]:.3f} x {size[1]:.3f} x {size[2]:.3f} m")
    print(f"kinematics: {kin_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
