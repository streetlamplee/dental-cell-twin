"""Dental product models for the milling line (run inside .venv-cad, CadQuery).

Our own simplified models (not clinical geometry), in millimetres, origin at the
bottom centre, Z up:
  dental_blank            14 x 12 x 16 block (CAD/CAM milling block)
  dental_crown            molar-like crown: rounded 11 x 10 body with four cusps
  dental_crown_incomplete crown + an uncut corner of blank material (tool breakage)

Usage: python scripts/make_dental_parts.py <out_dir>
"""

import sys
from pathlib import Path

import cadquery as cq


def blank() -> cq.Workplane:
    return cq.Workplane("XY").box(14, 12, 16, centered=(True, True, False)).edges("|Z").fillet(0.5)


def crown() -> cq.Workplane:
    body = (cq.Workplane("XY").box(11, 10, 6, centered=(True, True, False))
            .edges("|Z").fillet(3.0).faces(">Z").edges().fillet(1.2))
    cusps = cq.Workplane("XY")
    for x, y in ((2.4, 2.1), (-2.4, 2.1), (2.4, -2.1), (-2.4, -2.1)):
        cusps = cusps.union(cq.Workplane("XY").sphere(2.7).translate((x, y, 5.6)))
    shape = body.union(cusps)
    # Keep the cusps inside the body outline (no overhang seen from the top camera).
    trim = (cq.Workplane("XY").box(11, 10, 20, centered=(True, True, False)).edges("|Z").fillet(3.0))
    return shape.intersect(trim)


def crown_incomplete() -> cq.Workplane:
    remnant = cq.Workplane("XY").box(7.0, 6.0, 10.0, centered=False)  # +x/+y corner left unmilled
    return crown().union(remnant)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, wp in (("dental_blank", blank()), ("dental_crown", crown()),
                     ("dental_crown_incomplete", crown_incomplete())):
        asm = cq.Assembly(name=name).add(wp, name="body")
        path = out / f"{name}.step"
        asm.export(str(path), exportType="STEP")
        bb = wp.val().BoundingBox()
        print(f"{path.name}: {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f} mm, volume {wp.val().Volume():.0f} mm3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
