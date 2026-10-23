"""Inspection cell: the CAD-converted 5-axis machine standing in the line, with the inspection
camera on its spindle (Day 11; replaces the Day 5-7 mill station beside the belt).

The asset (assets/cad/teeth_mill.usd, written by the USD converter) is referenced, never
edited. Its links are siblings at their home-pose transforms (STEP has no joints), so joint
motion is applied by overriding each link's transform with forward kinematics from
kinematics.json. The motion itself (load, views, unload) comes from core.cell_cycle.

Added prims (not part of the asset):
  CameraRig  camera module on the spindle nose (collar + lens) and the USD camera; its world
             transform follows the spindle, so the inspection viewport moves with the machine
  Fixture    dark pad on the C platter: uniform background behind the crown in every view
The URDF's own tool, workpiece and marker are hidden.
"""

import json

import numpy as np
from pxr import Gf, Usd, UsdGeom

from . import scene_manager as scene
from .core import layout as L
from .core.cell_cycle import FIXTURE_THICKNESS, CellCycle, CellTiming, views_from_spec
from .core.urdf_model import model_from_kinematics

HIDDEN_PARTS = ("c_platter/work", "c_platter/marker", "z_slide/tool")


def _gf(t: np.ndarray, length_scale: float = 1.0) -> Gf.Matrix4d:
    m = np.array(t, dtype=float)
    m[:3, 3] *= length_scale
    return Gf.Matrix4d(m.T.tolist())  # USD uses row vectors: translation in the last row


def build_cycle(kinematics_path: str, spec) -> CellCycle:
    """CellCycle from kinematics.json + the catalog's cell spec (pure Python, no stage)."""
    with open(kinematics_path, encoding="utf-8") as f:
        model = model_from_kinematics(json.load(f))
    return CellCycle(model, views_from_spec(spec.views), CellTiming(**spec.timing), spec.standoff_m)


def _disc(stage, path, radius, height, color, segments=64):
    """Closed cylinder mesh with its top face at z = 0 (UsdGeom.Cylinder renders as a coarse
    polygon in RTX, and the pad's edge must stay round in the tilted views)."""
    ang = np.linspace(0.0, 2 * np.pi, segments, endpoint=False)
    ring = [(radius * np.cos(a), radius * np.sin(a)) for a in ang]
    points = [Gf.Vec3f(x, y, 0.0) for x, y in ring] + [Gf.Vec3f(x, y, -height) for x, y in ring]
    points += [Gf.Vec3f(0, 0, 0), Gf.Vec3f(0, 0, -height)]
    top, bottom = 2 * segments, 2 * segments + 1
    counts, idx = [], []
    for i in range(segments):
        j = (i + 1) % segments
        counts += [3, 3, 4]
        idx += [top, i, j, bottom, segments + j, segments + i, i, segments + i, segments + j, j]
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(points)
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(idx)
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    return mesh


def _cylinder(stage, path, radius, height, z, color):
    cyl = UsdGeom.Cylinder.Define(stage, path)
    cyl.CreateRadiusAttr(radius)
    cyl.CreateHeightAttr(height)
    cyl.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    UsdGeom.XformCommonAPI(cyl).SetTranslate(Gf.Vec3d(0.0, 0.0, z))
    return cyl


class InspectionCell:
    def __init__(self, stage: Usd.Stage, asset_path: str, kinematics_path: str, spec, cycle: CellCycle,
                 aperture_mm=(L.CAMERA_H_APERTURE_MM, L.CAMERA_V_APERTURE_MM)) -> None:
        with open(kinematics_path, encoding="utf-8") as f:
            kin = json.load(f)
        self.cycle = cycle
        self.model = cycle.model
        self.root = cycle.root(L.CELL_X, L.CONVEYOR_TOP_Z)  # product seat level with the belt
        self._links = sorted({v["link"] for v in kin["visuals"]})
        asset_mpu = UsdGeom.GetStageMetersPerUnit(Usd.Stage.Open(asset_path))
        self._unit = 1.0 / asset_mpu  # metres -> asset units (mm)

        # Stand from the floor to the machine base (base plate bottom = base frame z 0).
        rx, ry, rz = (float(v) for v in self.root[:3, 3])
        scene._box(stage, f"{L.CELL_PATH}/Stand", (rx, ry + 0.076, rz / 2.0), (0.56, 0.60, rz), (0.45, 0.45, 0.5))
        mill = UsdGeom.Xform.Define(stage, f"{L.CELL_PATH}/Machine")
        mill.GetPrim().GetReferences().AddReference(asset_path)
        xf = UsdGeom.XformCommonAPI(mill)
        xf.SetTranslate(Gf.Vec3d(rx, ry, rz))
        xf.SetScale(Gf.Vec3f(asset_mpu, asset_mpu, asset_mpu))  # asset is in mm, stage in m

        self._ops = {}
        for link in self._links:
            prim = stage.GetPrimAtPath(f"{L.CELL_PATH}/Machine/{self.model.name}/{link}")
            if not prim:
                raise RuntimeError(f"machine link prim not found: {link} (asset layout changed?)")
            x = UsdGeom.Xformable(prim)
            x.ClearXformOpOrder()
            self._ops[link] = x.AddTransformOp(opSuffix="joint")
        for part in HIDDEN_PARTS:
            prim = stage.GetPrimAtPath(f"{L.CELL_PATH}/Machine/{self.model.name}/{part}")
            if prim:
                prim.SetActive(False)

        # Camera module on the spindle nose; the optical centre is the rig origin.
        rig = UsdGeom.Xform.Define(stage, f"{L.CELL_PATH}/CameraRig")
        self._rig_op = rig.AddTransformOp()
        _cylinder(stage, f"{L.CELL_PATH}/CameraRig/Body", 0.031, 0.03, 0.017, (0.15, 0.15, 0.17))
        _cylinder(stage, f"{L.CELL_PATH}/CameraRig/Lens", 0.012, 0.004, 0.0, (0.02, 0.02, 0.03))
        cam = UsdGeom.Camera.Define(stage, L.CELL_CAMERA_PATH)  # looks down local -Z
        cam.CreateFocalLengthAttr(spec.focal_mm)
        cam.CreateHorizontalApertureAttr(aperture_mm[0])
        cam.CreateVerticalApertureAttr(aperture_mm[1])
        cam.CreateClippingRangeAttr(Gf.Vec2f(0.005, 100.0))

        fixture = UsdGeom.Xform.Define(stage, f"{L.CELL_PATH}/Fixture")
        self._fixture_op = fixture.AddTransformOp()
        _disc(stage, f"{L.CELL_PATH}/Fixture/Pad", 0.04, FIXTURE_THICKNESS, (0.05, 0.05, 0.06))
        self._seat = self.root @ cycle.product_seat(cycle.load_pose)
        self.apply(None)

    def apply(self, t_since_load, camera_offset=(0.0, 0.0, 0.0)) -> None:
        """Pose the machine `t_since_load` seconds into a cycle (None: idle at the load pose).
        camera_offset (world metres) only moves the camera (synthetic data jitter)."""
        q = self.cycle.pose_at(t_since_load)
        tf = self.model.link_transforms(q)
        for link, op in self._ops.items():
            op.Set(_gf(tf[link], self._unit))
        cam = self.root @ self.cycle.camera(q)
        cam[:3, 3] += np.asarray(camera_offset, dtype=float)
        self._rig_op.Set(_gf(cam))
        self._seat = self.root @ self.cycle.product_seat(q)
        self._fixture_op.Set(_gf(self._seat))

    def seat_pose(self) -> np.ndarray:
        """World 4x4 (metres) where the product's bottom centre sits at the last apply()."""
        return self._seat

    def phase(self, t_since_load) -> str:
        """Readable phase for the dashboard."""
        if t_since_load is None:
            return "idle"
        if t_since_load < self.cycle.timing.load_s:
            return "LOADING"
        k = self.cycle.view_at(t_since_load)
        if k is not None:
            return f"VIEW {k + 1}/{len(self.cycle.views)} {self.cycle.views[k].name}"
        if t_since_load >= self.cycle.unload_start:
            return "UNLOADING"
        return "MOVING"
