"""Conservative oriented-box interference tests, independent of USD/Kit.

Boxes enclose visible geometry; overlap is a potential collision, not mesh contact.
Trajectory sampling is discrete and cannot prove continuous collision freedom.
"""

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class Box:
    name: str
    center: np.ndarray
    half: np.ndarray
    axes: np.ndarray

    def __post_init__(self):
        for name, shape in (("center", (3,)), ("half", (3,)), ("axes", (3, 3))):
            value = np.array(getattr(self, name), dtype=float, copy=True)
            if value.shape != shape or not np.isfinite(value).all():
                raise ValueError(f"invalid box {name}: {self.name}")
            value.setflags(write=False)
            object.__setattr__(self, name, value)
        if np.any(self.half <= 0) or not np.allclose(self.axes.T @ self.axes, np.eye(3), atol=1e-7):
            raise ValueError(f"box needs positive extents and orthonormal axes: {self.name}")

    def moved(self, pose):
        return Box(self.name, pose[:3, :3] @ self.center + pose[:3, 3],
                   self.half, pose[:3, :3] @ self.axes)

    def aabb(self, margin=0.0):
        extent = np.abs(self.axes) @ (self.half + margin)
        return self.center - extent, self.center + extent


def overlaps(a, b, margin=0.0):
    """15-axis SAT. Touching counts; margin inflates each box by margin/2 per local axis.

    This is a box padding policy, not an exact Euclidean clearance calculation.
    """
    if not math.isfinite(margin) or margin < 0:
        raise ValueError("margin must be finite and nonnegative")
    ah, bh = a.half + margin / 2, b.half + margin / 2
    delta = b.center - a.center
    axes = [*a.axes.T, *b.axes.T]
    axes += [np.cross(x, y) for x in a.axes.T for y in b.axes.T]
    for axis in axes:
        length = np.linalg.norm(axis)
        if length < 1e-10:  # parallel axes have no separating cross product
            continue
        axis = axis / length
        radius = np.abs(a.axes.T @ axis) @ ah + np.abs(b.axes.T @ axis) @ bh
        if abs(delta @ axis) > radius + 1e-10:
            return False
    return True


def candidate_pairs(moving, obstacles, margin=0.0):
    """AABB broad phase followed by OBB SAT; return colliding box pairs."""
    if not math.isfinite(margin) or margin < 0:
        raise ValueError("margin must be finite and nonnegative")
    if not moving or not obstacles:
        return []
    bounds = [box.aabb(margin / 2) for box in obstacles]
    lows = np.array([b[0] for b in bounds])
    highs = np.array([b[1] for b in bounds])
    hits = []
    for box in moving:
        low, high = box.aabb(margin / 2)
        candidates = np.flatnonzero(np.all(high >= lows - 1e-10, axis=1) &
                                    np.all(low <= highs + 1e-10, axis=1))
        hits.extend((box, obstacles[i]) for i in candidates if overlaps(box, obstacles[i], margin))
    return hits


def sample_times(keys, max_dt=1 / 120, max_angle=math.radians(1), max_translation=0.002,
                 linear_joints=()):
    """Include endpoints and keyframes of smoothstep joint interpolation.

    The 1.5 factor bounds smoothstep's peak derivative, limiting each joint's
    increment between samples. It does not bound every surface point's motion.
    """
    if not all(math.isfinite(x) and x > 0 for x in (max_dt, max_angle, max_translation)):
        raise ValueError("sampling limits must be finite and positive")
    if len(keys) < 2 or any(not math.isfinite(t) for t, _ in keys):
        raise ValueError("at least two finite trajectory keyframes required")
    times = [keys[0][0]]
    for (t0, q0), (t1, q1) in zip(keys, keys[1:]):
        if t1 <= t0:
            raise ValueError("trajectory times must increase")
        if q0.keys() != q1.keys() or not all(math.isfinite(v) for v in (*q0.values(), *q1.values())):
            raise ValueError("trajectory joint values must be finite with matching keys")
        steps = max(1, math.ceil((t1 - t0) / max_dt))
        for joint in q0:
            limit = max_translation if joint in linear_joints else max_angle
            steps = max(steps, math.ceil(1.5 * abs(q1[joint] - q0[joint]) / limit))
        times.extend(np.linspace(t0, t1, steps + 1)[1:].tolist())
    return times


class CollisionBlocked(ValueError):
    """Preflight found potential interference; caller must not start this scene."""


def require_clear(report):
    if report["status"] != "clear_at_samples":
        first = report["contacts"][0]
        raise CollisionBlocked(f"collision preflight blocked: {first['phase']} at {first['time_s']:.4f}s, "
                               f"{first['robot']} vs {first['obstacle']}")
