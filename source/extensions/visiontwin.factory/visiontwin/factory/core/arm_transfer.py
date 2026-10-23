"""Robot arm transfer for the inspection cell (pure Python + numpy): Seeed reBot Arm B601-DM
moves products belt -> platter (load) and platter -> belt (unload).

Kinematics come from the robot's kinematics.json (core.urdf_model). The tool frame is
`end_link`: the gripper points along its +X, the fingers move along its Y. Every grasp is
top-down (tool +X = world -Z) with the fingers closing along world Y, so a product keeps its
yaw from belt to platter and back (the inspection views and calibrations depend on it).

Inverse kinematics: damped least squares on the six revolute joints, numerical Jacobian,
position + orientation error, joint limits clamped, several seeds. Every waypoint is solved
once when the transfer is built and checked against a tolerance, so a run never depends on
an IK solve during the simulation.

Each phase (load / unload) is a joint-space keyframe sequence that starts and ends at the
wait pose:  wait -> above pick -> pick (close) -> above pick -> above place -> place (open)
-> above place -> wait. Between grasp and release the product follows the tool.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .urdf_model import UrdfModel

ARM_JOINTS = ("joint1", "joint2", "joint3", "joint4", "joint5", "joint6")
TOOL_LINK = "end_link"
FINGERS = ("finger_left", "finger_right")
# Tool orientation for a top-down grasp: columns = tool X (approach, world -Z), tool Y
# (finger axis, world +Y), tool Z (= X x Y, world +X).
TOP_DOWN = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])
POS_TOL = 5e-4  # m
ROT_TOL = math.radians(1.0)


def _smooth(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def _rot_error(r_cur: np.ndarray, r_target: np.ndarray) -> np.ndarray:
    """Axis-angle vector (world frame) rotating r_cur onto r_target."""
    r = r_target @ r_cur.T
    axis = np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]])
    n = np.linalg.norm(axis)
    # atan2(sin, cos): acos((trace - 1) / 2) loses all precision for tiny angles, which made the
    # numerical rotation Jacobian zero and the orientation never converged.
    angle = math.atan2(n / 2.0, (np.trace(r) - 1.0) / 2.0)
    if angle < 1e-12:
        return np.zeros(3)
    if n < 1e-9:  # angle ~ pi: pick the dominant diagonal axis
        axis = np.sqrt(np.maximum((np.diag(r) + 1.0) / 2.0, 0.0))
        n = np.linalg.norm(axis)
    return axis / n * angle


class ArmModel:
    def __init__(self, model: UrdfModel, base: np.ndarray) -> None:
        """base: world <- robot base frame (4x4)."""
        self.model = model
        self.base = base
        self.limits = {j: (model.joints[j].lower, model.joints[j].upper) for j in ARM_JOINTS}
        self.finger_limits = {f: (model.joints[f].lower, model.joints[f].upper) for f in FINGERS}

    def tool(self, q: Dict[str, float]) -> np.ndarray:
        return self.base @ self.model.link_transforms(q)[TOOL_LINK]

    def _vec(self, q):
        return np.array([q.get(j, 0.0) for j in ARM_JOINTS])

    def _clamp(self, v: np.ndarray) -> np.ndarray:
        lo = np.array([self.limits[j][0] for j in ARM_JOINTS])
        hi = np.array([self.limits[j][1] for j in ARM_JOINTS])
        return np.clip(v, lo, hi)

    def solve(self, target: np.ndarray, seeds: Sequence[Dict[str, float]], iters: int = 300,
              damping: float = 0.05, random_seeds: int = 40) -> Tuple[Dict[str, float], float, float]:
        """IK for a world tool pose. Tries the given seeds first (continuity with the previous
        waypoint), then deterministic random seeds; stops at the first solution inside the
        tolerance. Returns (q, position error m, rotation error rad) of the best attempt."""
        rng = np.random.default_rng(0)
        extra = [{j: rng.uniform(*self.limits[j]) for j in ARM_JOINTS} for _ in range(random_seeds)]
        best = None
        for seed in list(seeds) + extra:
            v = self._clamp(self._vec(seed))
            for _ in range(iters):
                q = dict(zip(ARM_JOINTS, v))
                cur = self.tool(q)
                err = np.concatenate([target[:3, 3] - cur[:3, 3], _rot_error(cur[:3, :3], target[:3, :3])])
                if np.linalg.norm(err[:3]) < POS_TOL * 0.1 and np.linalg.norm(err[3:]) < ROT_TOL * 0.1:
                    break
                jac = np.zeros((6, 6))
                for i in range(6):
                    dv = v.copy()
                    dv[i] += 1e-6
                    d = self.tool(dict(zip(ARM_JOINTS, dv)))
                    jac[:3, i] = (d[:3, 3] - cur[:3, 3]) / 1e-6
                    jac[3:, i] = _rot_error(cur[:3, :3], d[:3, :3]) / 1e-6
                step = jac.T @ np.linalg.solve(jac @ jac.T + damping ** 2 * np.eye(6), err)
                v = self._clamp(v + step)
            q = dict(zip(ARM_JOINTS, v))
            cur = self.tool(q)
            pe = float(np.linalg.norm(target[:3, 3] - cur[:3, 3]))
            re = float(np.linalg.norm(_rot_error(cur[:3, :3], target[:3, :3])))
            if best is None or pe + re * 0.05 < best[1] + best[2] * 0.05:
                best = (q, pe, re)
            if pe <= POS_TOL and re <= ROT_TOL:
                break
        return best


@dataclass(frozen=True)
class TransferSpec:
    duration_s: float  # whole phase, wait -> ... -> wait
    approach_dz: float = 0.06  # above-pick / above-place height
    grasp_dz: float = 0.004  # tool centre above the product's bottom (crown centre)
    finger_open: float = 0.012  # each finger, metres from closed
    finger_closed: float = 0.0045
    hold_s: float = 0.15  # gripper close/open time


def _pose(xyz, rot=TOP_DOWN) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = rot
    m[:3, 3] = xyz
    return m


class ArmTransfer:
    """Load and unload trajectories between two product seats (4x4 world poses of a product's
    bottom centre): belt entry -> platter seat, platter seat -> belt exit."""

    # Fractions of the phase for the keyframes (move segments are equal, holds fixed).
    def __init__(self, arm: ArmModel, wait: Dict[str, float], entry: np.ndarray, seat: np.ndarray,
                 exit_: np.ndarray, spec: TransferSpec) -> None:
        self.arm, self.spec = arm, spec
        self.wait = dict(wait)
        self.phases = {"load": self._phase(entry, seat), "unload": self._phase(seat, exit_)}

    def _solve(self, xyz, seeds) -> Dict[str, float]:
        q, pe, re = self.arm.solve(_pose(xyz), seeds)
        if pe > POS_TOL or re > ROT_TOL:
            raise ValueError(f"IK failed at {np.round(xyz, 4).tolist()}: position error {pe * 1000:.2f} mm, "
                             f"rotation error {math.degrees(re):.2f} deg (out of reach or limits)")
        return q

    def _phase(self, pick: np.ndarray, place: np.ndarray):
        s = self.spec
        up = np.array([0.0, 0.0, s.approach_dz])
        g = np.array([0.0, 0.0, s.grasp_dz])
        seeds = [self.wait]
        above_pick = self._solve(pick[:3, 3] + g + up, seeds)
        at_pick = self._solve(pick[:3, 3] + g, [above_pick])
        above_place = self._solve(place[:3, 3] + g + up, [above_pick, self.wait])
        at_place = self._solve(place[:3, 3] + g, [above_place])
        # keyframes: (pose, gripper opening, product attached) with move/hold durations
        moves = 6  # wait->abovePick, ->pick, ->abovePick, ->abovePlace, ->place, ->abovePlace, then ->wait
        move_s = (s.duration_s - 2 * s.hold_s) / (moves + 1)
        if move_s <= 0:
            raise ValueError("transfer duration too short for the gripper holds")
        o, c = s.finger_open, s.finger_closed
        keys = [(0.0, self.wait, o), (move_s, above_pick, o), (move_s, at_pick, o), (s.hold_s, at_pick, c),
                (move_s, above_pick, c), (move_s, above_place, c), (move_s, at_place, c), (s.hold_s, at_place, o),
                (move_s, above_place, o), (move_s, self.wait, o)]
        t, timeline = 0.0, []
        for dt, q, grip in keys:
            t += dt
            timeline.append((t, q, grip))
        grasp_t = timeline[3][0]  # gripper closed on the product
        release_t = timeline[6][0]  # arrived at place; opens during the next hold
        grasp_tool = self.arm.tool(at_pick)
        return {"timeline": timeline, "grasp_t": grasp_t, "release_t": release_t,
                "tool_to_product": np.linalg.inv(grasp_tool) @ pick, "pick": pick, "place": place}

    def state(self, phase: str, t: float):
        """(arm joint values incl. fingers, product world pose or None if not carried,
        'before' | 'carried' | 'after') at `t` seconds into a load/unload phase."""
        ph = self.phases[phase]
        tl = ph["timeline"]
        t = min(max(t, 0.0), tl[-1][0])
        q, grip = tl[-1][1], tl[-1][2]
        for (t0, q0, g0), (t1, q1, g1) in zip(tl, tl[1:]):
            if t <= t1:
                k = _smooth((t - t0) / (t1 - t0)) if t1 > t0 else 1.0
                q = {j: q0[j] + (q1[j] - q0[j]) * k for j in ARM_JOINTS}
                grip = g0 + (g1 - g0) * k
                break
        full = dict(q)
        full["finger_left"], full["finger_right"] = grip, -grip
        if t < ph["grasp_t"]:
            return full, None, "before"
        if t < ph["release_t"]:
            return full, self.arm.tool(q) @ ph["tool_to_product"], "carried"
        return full, None, "after"

    def wait_pose(self) -> Dict[str, float]:
        full = dict(self.wait)
        full["finger_left"], full["finger_right"] = self.spec.finger_open, -self.spec.finger_open
        return full


def yaw_base(x: float, y: float, z: float, yaw_deg: float) -> np.ndarray:
    m = np.eye(4)
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    m[:3, :3] = [[c, -s, 0], [s, c, 0], [0, 0, 1]]
    m[:3, 3] = (x, y, z)
    return m
