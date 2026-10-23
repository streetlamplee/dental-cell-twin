"""Inspection cell cycle (pure Python + numpy): the 5-axis machine with a camera on its spindle.

The machine from reference/teeth_mill.urdf stands in line between two conveyor sections.
A product is loaded onto the C platter, then for each view the B/C axes tilt and turn it
while X/Z move the camera and Y moves the table so that the camera stays `standoff` metres
straight above the product centre (the camera looks down -Z, like the fixed one). After the
last view the camera parks aside and the product is unloaded onto the next belt.

Timeline (seconds after the product reached the station entry, i.e. after LOAD):
  [0, load_s)                 load: camera parked on the +X side, platter level
  per view: move_s, hold_s    move to the view pose, hold still; the frame is taken mid-hold
  move_s, unload_s            park the camera on the -X side, unload

Inverse kinematics is closed-form: X and Z only move the camera and Y only moves the table
(all prismatic, axis-aligned), so one linear step solves it. Every pose is checked against
the joint limits when the cycle is built.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .urdf_model import UrdfModel

PLATTER_TOP = 0.01  # c_platter frame: top face of the platter cylinder (URDF)
FIXTURE_THICKNESS = 0.002  # dark pad on the platter (uniform background for the camera)
CAMERA_OFFSET = (0.0, -0.04, -0.16)  # z_slide frame: centre of the spindle nose (URDF spindle)
CAMERA_LINK = "z_slide"
PLATTER_LINK = "c_platter"


@dataclass(frozen=True)
class View:
    name: str
    b_deg: float
    c_deg: float


@dataclass(frozen=True)
class CellTiming:
    load_s: float = 0.6
    move_s: float = 0.45
    hold_s: float = 0.3
    unload_s: float = 0.6


def _smooth(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def _translate(x, y, z) -> np.ndarray:
    t = np.eye(4)
    t[:3, 3] = (x, y, z)
    return t


class CellCycle:
    def __init__(self, model: UrdfModel, views: Sequence[View], timing: CellTiming = CellTiming(),
                 standoff: float = 0.11, target_dz: float = 0.004) -> None:
        """standoff: camera to product centre (m); target_dz: product centre above the pad."""
        if not views:
            raise ValueError("at least one view is required")
        self.model = model
        self.views = tuple(views)
        self.timing = timing
        self.standoff = standoff
        self.target_dz = target_dz
        self.limits = {n: (j.lower, j.upper) for n, j in model.joints.items() if j.type == "prismatic"}
        lo = {n: v[0] for n, v in self.limits.items()}
        hi = {n: v[1] for n, v in self.limits.items()}
        # Park poses: camera high and aside so the load/unload transfer passes under nothing.
        self.load_pose = {"x_joint": hi["x_joint"], "y_joint": 0.0, "z_joint": hi["z_joint"],
                          "b_joint": 0.0, "c_joint": 0.0}
        self.view_poses = [self._solve(v) for v in self.views]
        last_c = self.view_poses[-1]["c_joint"]
        self.unload_pose = {"x_joint": lo["x_joint"], "y_joint": 0.0, "z_joint": hi["z_joint"],
                            "b_joint": 0.0, "c_joint": 2 * math.pi * math.ceil(last_c / (2 * math.pi) - 1e-9)}
        for name, q in [("load", self.load_pose), ("unload", self.unload_pose)] + \
                [(v.name, q) for v, q in zip(self.views, self.view_poses)]:
            self._check_limits(name, q)

        t, keys = 0.0, [(0.0, self.load_pose)]
        t += timing.load_s
        keys.append((t, self.load_pose))
        self.view_times: List[float] = []
        for q in self.view_poses:
            t += timing.move_s
            keys.append((t, q))
            self.view_times.append(t + timing.hold_s / 2.0)
            t += timing.hold_s
            keys.append((t, q))
        t += timing.move_s
        keys.append((t, self.unload_pose))
        self.unload_start = t
        t += timing.unload_s
        keys.append((t, self.unload_pose))
        self.cycle_s = t
        self._keys = keys

    # -- kinematics ---------------------------------------------------------

    def _frames(self, q: Dict[str, float]):
        tf = self.model.link_transforms(q)
        cam = tf[CAMERA_LINK] @ _translate(*CAMERA_OFFSET)
        pad = tf[PLATTER_LINK] @ _translate(0.0, 0.0, PLATTER_TOP + FIXTURE_THICKNESS)
        return cam, pad

    def camera(self, q: Dict[str, float]) -> np.ndarray:
        """Base frame -> camera frame (looks down -Z, image right = +X, image up = +Y)."""
        return self._frames(q)[0]

    def product_seat(self, q: Dict[str, float]) -> np.ndarray:
        """Base frame -> top of the pad on the platter: where the product's bottom centre sits."""
        return self._frames(q)[1]

    def _target(self, q):
        return (self.product_seat(q) @ np.array([0.0, 0.0, self.target_dz, 1.0]))[:3]

    def _solve(self, view: View) -> Dict[str, float]:
        q = {"x_joint": 0.0, "y_joint": 0.0, "z_joint": 0.0,
             "b_joint": math.radians(view.b_deg), "c_joint": math.radians(view.c_deg)}
        cam, target = self.camera(q)[:3, 3], self._target(q)
        q["x_joint"] = float(target[0] - cam[0])  # x_joint moves the camera along +X
        q["y_joint"] = float(cam[1] - target[1])  # y_joint moves the table (and the product) along +Y
        q["z_joint"] = float(target[2] + self.standoff - cam[2])  # z_joint moves the camera along +Z
        return q

    def _check_limits(self, name: str, q: Dict[str, float]) -> None:
        for joint, (lo, hi) in self.limits.items():
            if not lo - 1e-9 <= q[joint] <= hi + 1e-9:
                raise ValueError(f"cell pose {name!r}: {joint}={q[joint]:.4f} outside [{lo:.4f}, {hi:.4f}]")

    def root(self, cell_x: float, seat_z: float) -> np.ndarray:
        """World <- base frame that puts the product seat of the load pose at (cell_x, 0, seat_z):
        the platter receives the product level with the belt, centred on the belt line."""
        seat = self.product_seat(self.load_pose)[:3, 3]
        return _translate(cell_x - seat[0], -seat[1], seat_z - seat[2])

    # -- timeline -----------------------------------------------------------

    def pose_at(self, t: Optional[float]) -> Dict[str, float]:
        """Joint values `t` seconds after loading started (None or out of the cycle: load pose)."""
        if t is None or t <= 0.0 or t >= self.cycle_s:
            return dict(self.load_pose)
        for (t0, q0), (t1, q1) in zip(self._keys, self._keys[1:]):
            if t <= t1:
                k = _smooth((t - t0) / (t1 - t0)) if t1 > t0 else 1.0
                return {j: q0[j] + (q1[j] - q0[j]) * k for j in q0}
        return dict(self.load_pose)

    def view_at(self, t: float) -> Optional[int]:
        """Index of the view whose hold window contains t, else None."""
        for i, vt in enumerate(self.view_times):
            if abs(t - vt) <= self.timing.hold_s / 2.0:
                return i
        return None


def views_from_spec(spec: Sequence[dict]) -> Tuple[View, ...]:
    return tuple(View(str(v["name"]), float(v["b_deg"]), float(v["c_deg"])) for v in spec)
