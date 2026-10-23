"""URDF -> STEP assembly + kinematics.json (run inside .venv-cad, CadQuery).

STEP layout: <robot> / <link> (located at the link's home-pose world transform) /
<part> (one solid per box/cylinder visual, located at the visual origin, coloured).
Lengths are written in millimetres (CAD convention). STEP carries geometry only, so the
joints go to <out>.kinematics.json, which also maps every visual to its STEP part name.

Usage: python scripts/urdf_to_step.py <urdf> <out.stp>
"""

import json
import sys
from pathlib import Path

import cadquery as cq
from OCP.gp import gp_Trsf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/extensions/visiontwin.factory/visiontwin/factory"))

from core.urdf_model import load_urdf  # noqa: E402

MM = 1000.0  # metres -> millimetres
FILLET_FRACTION = 0.12  # box edge fillet radius / smallest box side
CHAMFER_FRACTION = 0.1  # cylinder end chamfer / min(radius, length)


def location(t) -> cq.Location:
    """4x4 (metres) -> cq.Location (millimetres)."""
    trsf = gp_Trsf()
    r, p = t[:3, :3], t[:3, 3] * MM
    trsf.SetValues(r[0, 0], r[0, 1], r[0, 2], p[0],
                   r[1, 0], r[1, 1], r[1, 2], p[1],
                   r[2, 0], r[2, 1], r[2, 2], p[2])
    return cq.Location(trsf)


def solid(visual) -> cq.Workplane:
    """Centred at the visual frame origin; a cylinder's axis is its local Z (URDF).

    Machined-looking detail without changing the URDF envelope: box edges are filleted and
    cylinder ends chamfered. Flat faces still reach the URDF size, so every part's bounding
    box is unchanged (verify_cad_usd checks it)."""
    if visual.shape == "box":
        x, y, z = (s * MM for s in visual.size)
        return cq.Workplane("XY").box(x, y, z).edges().fillet(min(x, y, z) * FILLET_FRACTION)
    radius, length = (s * MM for s in visual.size)
    return cq.Workplane("XY").cylinder(length, radius).edges("%CIRCLE").chamfer(min(radius, length) * CHAMFER_FRACTION)


def part_name(link_name: str, visual_name: str) -> str:
    return f"{visual_name}_shape" if visual_name == link_name else visual_name


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    urdf, out = Path(sys.argv[1]), Path(sys.argv[2])
    model = load_urdf(str(urdf))
    home = model.link_transforms()

    robot = cq.Assembly(name=model.name)
    mapping = []
    for link in model.links.values():
        if not link.visuals:
            continue
        link_asm = cq.Assembly(name=link.name)
        for v in link.visuals:
            name = part_name(link.name, v.name)
            link_asm.add(solid(v), name=name, loc=location(v.origin), color=cq.Color(*v.rgba))
            mapping.append({"link": link.name, "visual": v.name, "part": name, "shape": v.shape,
                            "size_m": list(v.size), "rgba": list(v.rgba)})
        robot.add(link_asm, name=link.name, loc=location(home[link.name]))

    out.parent.mkdir(parents=True, exist_ok=True)
    robot.export(str(out), exportType="STEP")  # ".stp" is not auto-detected

    kin = model.kinematics()
    kin["source"] = urdf.name
    kin["step"] = {"file": out.name, "length_unit": "mm", "pose": "home (all joint values 0)",
                   "hierarchy": f"{model.name}/<link>/<part>"}
    kin["visuals"] = mapping
    kin_path = out.with_suffix(".kinematics.json")
    kin_path.write_text(json.dumps(kin, indent=2), encoding="utf-8")
    print(f"STEP: {out} ({out.stat().st_size} bytes), links={len({m['link'] for m in mapping})}, parts={len(mapping)}")
    print(f"kinematics: {kin_path} (joints={len(kin['joints'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
