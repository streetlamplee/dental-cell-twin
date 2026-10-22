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


class MillStation:
    def __init__(self, stage: Usd.Stage, asset_path: str, kinematics_path: str) -> None:
        with open(kinematics_path, encoding="utf-8") as f:
            kin = json.load(f)
        self.model = model_from_kinematics(kin)
        limits = {n: (j.lower, j.upper) for n, j in self.model.joints.items() if j.type == "prismatic"}
        self.cycle = MillCycle(limits)
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
        self.apply(0.0)

    def apply(self, t: float) -> None:
        transforms = self.model.link_transforms(self.cycle.joint_values(t))
        for link, op in self._ops.items():
            op.Set(_gf(transforms[link], self._unit))
