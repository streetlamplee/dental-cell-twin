"""Mill station: the CAD-converted teeth_mill USD placed beside the line, with joint motion.

The asset (assets/cad/teeth_mill.usd, written by the USD converter) is referenced, never
edited. Its links are siblings at their home-pose transforms (STEP has no joints), so
joint motion is applied by overriding each link's transform with forward kinematics
from kinematics.json (core.urdf_model). Visual only.
"""

import json

import numpy as np
from pxr import Gf, Usd, UsdGeom

from . import scene_manager as scene
from .core import layout as L
from .core.mill_cycle import MillCycle
from .core.urdf_model import model_from_kinematics


def _gf(t: np.ndarray, length_scale: float) -> Gf.Matrix4d:
    m = np.array(t, dtype=float)
    m[:3, 3] *= length_scale
    return Gf.Matrix4d(m.T.tolist())  # USD uses row vectors: translation in the last row


PLATTER_TOP = 0.01  # c_platter frame: top face of the platter cylinder (URDF), metres


class MillStation:
    def __init__(self, stage: Usd.Stage, asset_path: str, kinematics_path: str,
                 hide_work: bool = False, cycle_duration: float = 3.0) -> None:
        """hide_work: hide the URDF's own workpiece/marker (the dental line puts the real
        product on the platter instead). cycle_duration: machining motion length (sim s)."""
        with open(kinematics_path, encoding="utf-8") as f:
            kin = json.load(f)
        self.model = model_from_kinematics(kin)
        limits = {n: (j.lower, j.upper) for n, j in self.model.joints.items() if j.type == "prismatic"}
        self.cycle = MillCycle(limits, duration=cycle_duration)
        self._root = np.eye(4)
        self._root[:3, 3] = (L.MILL_X, L.MILL_Y, L.MILL_STAND_HEIGHT)
        self._transforms = self.model.link_transforms()
        self._links = sorted({v["link"] for v in kin["visuals"]})

        asset_mpu = UsdGeom.GetStageMetersPerUnit(Usd.Stage.Open(asset_path))
        self._unit = 1.0 / asset_mpu  # metres -> asset units (mm)

        stand_top = L.MILL_STAND_HEIGHT
        scene._box(stage, f"{L.MILL_PATH}/Stand", (L.MILL_X, L.MILL_Y + 0.1, stand_top / 2.0),
                   (0.6, 0.7, stand_top), (0.45, 0.45, 0.5))
        mill = UsdGeom.Xform.Define(stage, f"{L.MILL_PATH}/Mill")
        mill.GetPrim().GetReferences().AddReference(asset_path)
        xf = UsdGeom.XformCommonAPI(mill)
        xf.SetTranslate(Gf.Vec3d(L.MILL_X, L.MILL_Y, stand_top))
        xf.SetScale(Gf.Vec3f(asset_mpu, asset_mpu, asset_mpu))  # asset is in mm, stage in m

        # Link prims inside the reference: <Mill>/<robot>/<link>. Replace their xform ops with a
        # single transform op that we drive.
        self._ops = {}
        for link in self._links:
            prim = stage.GetPrimAtPath(f"{L.MILL_PATH}/Mill/{self.model.name}/{link}")
            if not prim:
                raise RuntimeError(f"mill link prim not found: {link} (asset layout changed?)")
            x = UsdGeom.Xformable(prim)
            x.ClearXformOpOrder()
            self._ops[link] = x.AddTransformOp(opSuffix="joint")
        if hide_work:
            for part in ("work", "marker"):
                prim = stage.GetPrimAtPath(f"{L.MILL_PATH}/Mill/{self.model.name}/c_platter/{part}")
                if prim:
                    prim.SetActive(False)
        self.apply(0.0)

    def apply(self, t: float) -> None:
        self._transforms = self.model.link_transforms(self.cycle.joint_values(t))
        for link, op in self._ops.items():
            op.Set(_gf(self._transforms[link], self._unit))

    def platter_pose(self) -> np.ndarray:
        """World 4x4 (metres) of the platter's top-centre at the last apply(): where a
        workpiece sits, including the B/C rotation."""
        top = np.eye(4)
        top[2, 3] = PLATTER_TOP
        return self._root @ self._transforms["c_platter"] @ top
