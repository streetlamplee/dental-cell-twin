"""Transfer robot in the inspection cell: Seeed reBot Arm B601-DM (Day 12).

The robot USD comes from scripts/urdf_mesh_to_usd.ps1 (links are siblings at their home-pose
transforms, metres). It is referenced, never edited; joint motion overrides each link's
transform with forward kinematics from the robot's kinematics.json, like the machine.
The trajectories themselves (IK, pick-and-place keyframes) are computed in core.arm_transfer.
"""

import json

import numpy as np
from pxr import Gf, Usd, UsdGeom

from . import scene_manager as scene
from .core import layout as L
from .core.arm_transfer import ArmModel, ArmTransfer, TransferSpec, yaw_base
from .core.urdf_model import model_from_kinematics


def _gf(t: np.ndarray) -> Gf.Matrix4d:
    return Gf.Matrix4d(np.asarray(t, dtype=float).T.tolist())  # USD uses row vectors


def build_transfer(kinematics_path: str, entry: np.ndarray, seat: np.ndarray, exit_: np.ndarray,
                   load_s: float, unload_s: float) -> ArmTransfer:
    """ArmTransfer for the cell (pure Python, solved once). load_s and unload_s must match."""
    if abs(load_s - unload_s) > 1e-9:
        raise ValueError("the arm uses one duration for load and unload")
    with open(kinematics_path, encoding="utf-8") as f:
        model = model_from_kinematics(json.load(f))
    arm = ArmModel(model, yaw_base(*L.ARM_BASE, L.ARM_YAW_DEG))
    return ArmTransfer(arm, L.ARM_WAIT, entry, seat, exit_, TransferSpec(load_s))


class RobotArm:
    def __init__(self, stage: Usd.Stage, asset_path: str, transfer: ArmTransfer) -> None:
        self.transfer = transfer
        model = transfer.arm.model
        bx, by, bz = L.ARM_BASE
        scene._box(stage, f"{L.ARM_PATH}_Pedestal", (bx, by, bz / 2.0), (0.16, 0.16, bz), (0.3, 0.3, 0.33))
        robot = UsdGeom.Xform.Define(stage, L.ARM_PATH)
        robot.GetPrim().GetReferences().AddReference(asset_path)
        robot.AddTransformOp().Set(_gf(transfer.arm.base))
        root = stage.GetPrimAtPath(L.ARM_PATH)
        self._ops = {}
        for link in model.links:
            prim = root.GetChild(link) if root else None
            if not prim:
                raise RuntimeError(f"robot link prim not found: {link} (asset layout changed?)")
            x = UsdGeom.Xformable(prim)
            x.ClearXformOpOrder()
            self._ops[link] = x.AddTransformOp(opSuffix="joint")
        self.apply(transfer.wait_pose())

    def apply(self, q) -> None:
        tf = self.transfer.arm.model.link_transforms(q)
        for link, op in self._ops.items():
            op.Set(_gf(tf[link]))
