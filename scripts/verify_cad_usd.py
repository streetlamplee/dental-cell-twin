"""Verify a converted CAD USD against its URDF (run inside .venv-cad: usd-core + numpy).

Checks, in metres after applying the stage's metersPerUnit:
  1. every link and every visual part from <stp>.kinematics.json exists at
     /<defaultPrim>/<robot>/<link>/<part>
  2. each link prim's world translation == the URDF home-pose link origin
  3. each part's world AABB == the analytic AABB of the URDF box/cylinder
     (box tolerance 0.1 mm; cylinders allow the tessellation chord error)
  4. each part's bound material colour == the URDF rgba (when materials were converted)
Writes <usd>.verify.json and exits 1 on any failure.

Usage: python scripts/verify_cad_usd.py <urdf> <usd> <kinematics.json>
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
from pxr import Usd, UsdGeom, UsdShade

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/extensions/visiontwin.factory/visiontwin/factory"))

from core.urdf_model import load_urdf  # noqa: E402

BOX_TOL_M = 0.0001
LINK_TOL_M = 0.0001
CYL_CHORD_FRACTION = 0.05  # tessellated circle may be inside the true circle by up to 5% of r


def expected_aabb(visual, world):
    r, c = world[:3, :3], world[:3, 3]
    if visual.shape == "box":
        half = np.array(visual.size) / 2.0
        ext = np.abs(r) @ half
        return c - ext, c + ext, 0.0
    radius, length = visual.size
    a = r[:, 2]  # cylinder axis in world
    ext = np.abs(a) * length / 2.0 + radius * np.sqrt(np.clip(1.0 - a * a, 0.0, 1.0))
    return c - ext, c + ext, radius * CYL_CHORD_FRACTION


def material_rgb(prim):
    """diffuseColor of the material bound to the part's mesh.

    The converter binds materials on the Mesh under each part (inside an instance), and the
    colour is an input on the Material that the PreviewSurface shader connects to.
    """
    for p in Usd.PrimRange(prim, Usd.TraverseInstanceProxies()):
        if p.GetTypeName() != "Mesh":
            continue
        mat, _ = UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial()
        if not mat:
            continue
        inp = mat.GetInput("diffuseColor")
        if inp and inp.Get() is not None:
            return tuple(float(x) for x in inp.Get())
        for child in Usd.PrimRange(mat.GetPrim()):
            sh = UsdShade.Shader(child)
            src = sh.GetInput("diffuseColor") if sh else None
            if src:
                for attr in src.GetValueProducingAttributes():
                    if attr.Get() is not None:
                        return tuple(float(x) for x in attr.Get())
    return None


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    urdf_path, usd_path, kin_path = (Path(a) for a in sys.argv[1:])
    model = load_urdf(str(urdf_path))
    kin = json.loads(kin_path.read_text(encoding="utf-8"))
    stage = Usd.Stage.Open(str(usd_path))
    mpu = UsdGeom.GetStageMetersPerUnit(stage)
    base = f"{stage.GetDefaultPrim().GetPath()}/{model.name}"
    home = model.link_transforms()
    visuals = {(link, v.name): v for link, v in model.visuals()}
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_], useExtentsHint=False)
    xcache = UsdGeom.XformCache()

    report = {"usd": usd_path.name, "metersPerUnit": mpu, "upAxis": UsdGeom.GetStageUpAxis(stage),
              "links": [], "parts": [], "failures": []}

    for link in sorted({m["link"] for m in kin["visuals"]}):
        prim = stage.GetPrimAtPath(f"{base}/{link}")
        if not prim:
            report["failures"].append(f"link prim missing: {base}/{link}")
            continue
        pos = np.array(xcache.GetLocalToWorldTransform(prim).ExtractTranslation()) * mpu
        err = float(np.max(np.abs(pos - home[link][:3, 3])))
        report["links"].append({"link": link, "position_error_mm": round(err * 1000, 4)})
        if err > LINK_TOL_M:
            report["failures"].append(f"link {link} position off by {err * 1000:.3f} mm")

    for m in kin["visuals"]:
        path = f"{base}/{m['link']}/{m['part']}"
        prim = stage.GetPrimAtPath(path)
        if not prim:
            report["failures"].append(f"part prim missing: {path}")
            continue
        v = visuals[(m["link"], m["visual"])]
        lo_e, hi_e, chord = expected_aabb(v, home[m["link"]] @ v.origin)
        rng = cache.ComputeWorldBound(prim).ComputeAlignedRange()
        lo, hi = np.array(rng.GetMin()) * mpu, np.array(rng.GetMax()) * mpu
        # Measured box may be smaller than the analytic one by the chord error (never larger).
        dev_out = float(max(np.max(lo_e - lo), np.max(hi - hi_e)))  # measured outside expected
        dev_in = float(max(np.max(lo - lo_e), np.max(hi_e - hi)))   # measured inside expected
        ok = dev_out <= BOX_TOL_M and dev_in <= BOX_TOL_M + chord
        rgb = material_rgb(prim)
        color_err = None if rgb is None else float(np.max(np.abs(np.array(rgb) - np.array(v.rgba[:3]))))
        report["parts"].append({"part": m["part"], "shape": v.shape,
                                "outside_mm": round(dev_out * 1000, 4), "inside_mm": round(dev_in * 1000, 4),
                                "color_error": None if color_err is None else round(color_err, 4)})
        if not ok:
            report["failures"].append(f"part {m['part']} bbox off: outside {dev_out * 1000:.3f} mm, "
                                      f"inside {dev_in * 1000:.3f} mm (chord allowance {chord * 1000:.2f} mm)")
        if color_err is not None and color_err > 0.02:
            report["failures"].append(f"part {m['part']} colour {rgb} != urdf {v.rgba[:3]}")

    out = usd_path.with_suffix(".verify.json")
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    worst_in = max((p["inside_mm"] for p in report["parts"]), default=0)
    worst_out = max((p["outside_mm"] for p in report["parts"]), default=0)
    colours = sum(p["color_error"] is not None for p in report["parts"])
    print(f"metersPerUnit={mpu} upAxis={report['upAxis']}")
    print(f"links matched: {len(report['links'])}/{len({m['link'] for m in kin['visuals']})}, "
          f"parts matched: {len(report['parts'])}/{len(kin['visuals'])}, colours checked: {colours}")
    print(f"worst bbox deviation: outside {worst_out} mm, inside {worst_in} mm")
    if report["failures"]:
        print(f"FAILED ({len(report['failures'])}):")
        for f in report["failures"]:
            print("  " + f)
        return 1
    print(f"VERIFIED -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
