"""Visual machining cycle for the mill station (pure Python).

A cycle starts when a product crosses the station line and lasts `duration` seconds of
simulation time. Joint targets stay inside the joint limits. Visual only: nothing in the
inspection or sorting logic reads these values.
"""

import math
from typing import Dict, Optional

# Keyframes as (phase 0..1, fraction of each prismatic range, b angle, c turns).
# Fractions are applied between lower (0.0) and upper (1.0) limits.
_KEYS = [
    (0.00, {"x_joint": 0.5, "y_joint": 0.5, "z_joint": 1.0}, 0.0, 0.0),
    (0.20, {"x_joint": 0.5, "y_joint": 0.2, "z_joint": 1.0}, 0.0, 0.0),
    (0.40, {"x_joint": 0.4, "y_joint": 0.2, "z_joint": 0.1}, math.radians(15), 0.25),
    (0.70, {"x_joint": 0.6, "y_joint": 0.3, "z_joint": 0.1}, math.radians(-15), 0.75),
    (0.85, {"x_joint": 0.5, "y_joint": 0.3, "z_joint": 1.0}, 0.0, 1.0),
    (1.00, {"x_joint": 0.5, "y_joint": 0.5, "z_joint": 1.0}, 0.0, 1.0),
]


def _smooth(u: float) -> float:
    return u * u * (3 - 2 * u)


class MillCycle:
    def __init__(self, limits: Dict[str, tuple], duration: float = 3.0) -> None:
        """limits: joint name -> (lower, upper) for the prismatic joints."""
        self.limits = limits
        self.duration = duration
        self.start_time: Optional[float] = None
        self.cycles = 0

    @property
    def busy(self) -> bool:
        return self.start_time is not None

    def trigger(self, t: float) -> bool:
        """Start a cycle at sim time t unless one is running. Returns True if started."""
        if self.busy:
            return False
        self.start_time = t
        self.cycles += 1
        return True

    def joint_values(self, t: float) -> Dict[str, float]:
        """Joint values at sim time t (home pose of the cycle when idle)."""
        u = 0.0
        if self.busy:
            u = (t - self.start_time) / self.duration
            if u >= 1.0:
                self.start_time = None
                u = 1.0
        u = min(max(u, 0.0), 1.0)
        for (p0, f0, b0, c0), (p1, f1, b1, c1) in zip(_KEYS, _KEYS[1:]):
            if u <= p1:
                k = _smooth((u - p0) / (p1 - p0)) if p1 > p0 else 1.0
                break
        q = {}
        for name, (lo, hi) in self.limits.items():
            frac = f0.get(name, 0.5) + (f1.get(name, 0.5) - f0.get(name, 0.5)) * k
            q[name] = lo + (hi - lo) * frac
        q["b_joint"] = b0 + (b1 - b0) * k
        q["c_joint"] = 2 * math.pi * (c0 + (c1 - c0) * k)
        return q
