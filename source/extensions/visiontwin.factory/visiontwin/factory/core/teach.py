"""Surface teaching for the 5-axis machine (pure Python + numpy), Day 13.

Recreates a teaching exercise done on the real dental mill: the tool looks straight down at
each face of the block on the C platter (top + 4 sides) and a 6th point is the origin.
The URDF's own workpiece (`c_platter/work`, 35 x 35 x 20 mm) is the block.

A side face can only look up when B tilts the platter by 90 deg; C then picks which side.
For a face, the joint values come from closed-form IK like the inspection cell (X and Z move
the tool, Y moves the table), with the tool tip `standoff` metres above the face centre.

verify() measures any pose (generated or jogged by hand on the pendant) against the faces:
tool-axis angle to the face normal, lateral offset of the tool tip from the face centre,
standoff along the tool axis, joint limits. A teach program is a list of named points saved
as JSON; play() interpolates between them like the cell cycle (move, hold).
"""

import json
import math
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .urdf_model import UrdfModel

AXES = ("x_joint", "y_joint", "z_joint", "b_joint", "c_joint")
TOOL_LINK = "tool_tip"
PLATTER_LINK = "c_platter"
FACES = {"top": (0, 0, 1), "side_+x": (1, 0, 0), "side_-x": (-1, 0, 0), "side_+y": (0, 1, 0), "side_-y": (0, -1, 0)}


@dataclass
class TeachPoint:
    name: str
    q: Dict[str, float]
    face: Optional[str] = None  # face the point was taught for (None: origin / free point)
    source: str = "auto"  # "auto" (generated) or "manual" (pendant)


@dataclass
class FaceCheck:
    face: str
    angle_deg: float  # tool axis vs face normal (0 = looking straight at the face)
    offset_mm: float  # tool tip distance from the face-centre line
    standoff_mm: float  # tool tip to face plane along the normal
    within_limits: bool


def _smooth(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


class Teacher:
    def __init__(self, model: UrdfModel, block_size: Sequence[float], block_origin: np.ndarray) -> None:
        """block_size: (x, y, z) metres; block_origin: c_platter frame -> block centre (4x4)."""
        self.model = model
        self.half = np.asarray(block_size, dtype=float) / 2.0
        self.block = np.asarray(block_origin, dtype=float)
        self.limits = {n: (j.lower, j.upper) for n, j in model.joints.items() if j.type == "prismatic"}

    @classmethod
    def from_urdf(cls, model: UrdfModel, part: str = "work") -> "Teacher":
        v = next(v for v in model.links[PLATTER_LINK].visuals if v.name == part)
        return cls(model, v.size, v.origin)

    # -- geometry -----------------------------------------------------------

    def face_frame(self, face: str, q: Dict[str, float]) -> Tuple[np.ndarray, np.ndarray]:
        """(face centre, outward normal) in the machine base frame at joint values q."""
        n_local = np.array(FACES[face], dtype=float)
        tf = self.model.link_transforms(q)[PLATTER_LINK] @ self.block
        centre = tf @ np.r_[n_local * self.half, 1.0]
        return centre[:3], tf[:3, :3] @ n_local

    def tool(self, q: Dict[str, float]) -> Tuple[np.ndarray, np.ndarray]:
        """(tool tip, tool axis pointing out of the spindle) in the base frame."""
        tf = self.model.link_transforms(q)[TOOL_LINK]
        return tf[:3, 3], -tf[:3, 2]

    def within_limits(self, q: Dict[str, float]) -> bool:
        return all(lo - 1e-9 <= q[j] <= hi + 1e-9 for j, (lo, hi) in self.limits.items())

    # -- teaching -----------------------------------------------------------

    def solve_face(self, face: str, standoff: float) -> Tuple[Optional[Dict[str, float]], Dict[str, float]]:
        """Joint values with the tool `standoff` above the face centre, looking at it.
        Returns (q or None if unreachable, the closest attempt) over B in {0, -90, +90} deg and
        C in {0, 90, 180, 270} deg (the orientations that turn the face up). B -90 comes first:
        the tilted platter then faces the front (-Y), where the operator stands; at +90 the
        cradle hides the block from the front (seen in the first renders)."""
        attempt = None
        for b in (0.0, -90.0, 90.0):
            for c in (0.0, 90.0, 180.0, 270.0):
                q = {"x_joint": 0.0, "y_joint": 0.0, "z_joint": 0.0, "b_joint": math.radians(b), "c_joint": math.radians(c)}
                centre, normal = self.face_frame(face, q)
                if normal[2] < 0.999:
                    continue
                target = centre + normal * standoff
                tip, _ = self.tool(q)
                q["x_joint"] = float(target[0] - tip[0])  # X moves the tool along +X
                q["y_joint"] = float(tip[1] - target[1])  # Y moves the table (and the block) along +Y
                q["z_joint"] = float(target[2] - tip[2])  # Z moves the tool along +Z
                if self.within_limits(q):
                    return q, q
                attempt = attempt or q
        return None, attempt

    def face_program(self, standoff: float) -> List[TeachPoint]:
        """Origin + the five faces. Raises ValueError naming the faces out of reach."""
        points = [TeachPoint("origin", {a: 0.0 for a in AXES}, None)]
        missing = []
        for face in FACES:
            q, attempt = self.solve_face(face, standoff)
            if q is None:
                bad = {j: round(attempt[j] * 1000, 1) for j, (lo, hi) in self.limits.items()
                       if not lo <= attempt[j] <= hi} if attempt else {}
                missing.append(f"{face} (needs {bad} mm)")
            else:
                points.append(TeachPoint(face, q, face))
        if missing:
            raise ValueError(f"standoff {standoff * 1000:.0f} mm: out of reach: {', '.join(missing)}")
        return points

    def verify(self, q: Dict[str, float], face: Optional[str] = None) -> FaceCheck:
        """Measure a pose against `face`, or against the face it is closest to looking at."""
        tip, axis = self.tool(q)
        best = None
        for f in ([face] if face else FACES):
            centre, normal = self.face_frame(f, q)
            angle = math.degrees(math.acos(min(max(float(-axis @ normal), -1.0), 1.0)))
            rel = tip - centre
            standoff = float(rel @ normal)
            lateral = float(np.linalg.norm(rel - normal * standoff))
            check = FaceCheck(f, angle, lateral * 1000.0, standoff * 1000.0, self.within_limits(q))
            if best is None or (check.angle_deg, check.offset_mm) < (best.angle_deg, best.offset_mm):
                best = check
        return best


class TeachProgram:
    def __init__(self, points: Sequence[TeachPoint], move_s: float = 1.0, hold_s: float = 0.5) -> None:
        if not points:
            raise ValueError("empty program")
        self.points = list(points)
        self.move_s, self.hold_s = move_s, hold_s

    @property
    def duration(self) -> float:
        return len(self.points) * (self.move_s + self.hold_s)

    def hold_time(self, i: int) -> float:
        """Middle of the hold at point i (where a picture is taken)."""
        return i * (self.move_s + self.hold_s) + self.move_s + self.hold_s / 2.0

    def pose_at(self, t: float, start: Optional[Dict[str, float]] = None) -> Tuple[Dict[str, float], int]:
        """(joint values, index of the point being approached/held) t seconds into playback,
        starting from `start` (default: the first point)."""
        prev = dict(start or self.points[0].q)
        for i, p in enumerate(self.points):
            t0 = i * (self.move_s + self.hold_s)
            if t < t0 + self.move_s:
                k = _smooth((t - t0) / self.move_s)
                return {a: prev[a] + (p.q[a] - prev[a]) * k for a in AXES}, i
            if t < t0 + self.move_s + self.hold_s:
                return dict(p.q), i
            prev = p.q
        return dict(self.points[-1].q), len(self.points) - 1

    def to_json(self, **meta) -> str:
        return json.dumps({**meta, "move_s": self.move_s, "hold_s": self.hold_s,
                           "points": [asdict(p) for p in self.points]}, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "TeachProgram":
        d = json.loads(text)
        return cls([TeachPoint(**p) for p in d["points"]], d.get("move_s", 1.0), d.get("hold_s", 0.5))
