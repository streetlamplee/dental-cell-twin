"""Time-stepped conveyor simulation.

Positions advance by simulation time `dt`, not by render frames, and line
crossings are detected on the segment [x_before, x_after], so a large dt
cannot skip an inspection or reject line.
"""

import random
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from . import layout as L
from .product_tracker import DEFECT, GOOD, Product, ProductState, ProductTracker

# Event kinds
SPAWN = "SPAWN"
INSPECT = "INSPECT"  # crossed the inspection line
SORT = "SORT"  # crossed the reject line and stayed on the belt
REJECT = "REJECT"  # crossed the reject line and was pushed off
EXIT = "EXIT"  # left the line (end of belt or into the reject bin)
STATION = "STATION"  # crossed a station line (e.g. the mill); `station` names it


@dataclass(frozen=True)
class LineEvent:
    time: float
    product_id: int
    kind: str
    x: float
    station: str = ""


@dataclass
class ConveyorConfig:
    seed: int = 42
    speed: float = 0.5  # m/s
    spawn_interval: float = 1.5  # s
    defect_rate: float = 0.3
    max_products: int = 30
    min_gap: float = L.PRODUCT_SIZE * 1.5  # spawn waits until the previous product moved this far
    stations: Tuple[Tuple[str, float], ...] = ()  # (name, x): visual stations, emit STATION events


# Returns True if the product must be pushed off at the reject line.
RejectDecider = Callable[[Product], bool]


class ConveyorSim:
    def __init__(self, config: Optional[ConveyorConfig] = None,
                 reject_decider: Optional[RejectDecider] = None) -> None:
        self.config = config or ConveyorConfig()
        self.reject_decider = reject_decider or (lambda _p: False)
        self.reset()

    def reset(self) -> None:
        self.tracker = ProductTracker()
        self.time = 0.0
        self.running = False
        self._rng = random.Random(self.config.seed)
        self._next_spawn_time = 0.0
        self._spawned = 0

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def set_speed(self, speed: float) -> None:
        if speed < 0:
            raise ValueError("speed must be >= 0")
        self.config.speed = speed

    @property
    def finished(self) -> bool:
        return self._spawned >= self.config.max_products and not self.tracker.on_belt()

    def step(self, dt: float) -> List[LineEvent]:
        """Advance the simulation by dt seconds and return events in time order."""
        if not self.running or dt <= 0:
            return []
        t0, t1 = self.time, self.time + dt
        events: List[LineEvent] = []

        # Move products already on the belt during [t0, t1].
        for p in sorted(self.tracker.on_belt(), key=lambda p: -p.x):
            events.extend(self._advance(p, t0, t1))

        # Spawn products scheduled inside this step, then move them for the remaining time.
        while self._spawned < self.config.max_products and self._next_spawn_time <= t1:
            t_clear = self._spawn_clear_time(t1)
            if t_clear is None:
                break  # retry next step; schedule slips instead of overlapping products
            ts = max(self._next_spawn_time, t0, t_clear)
            p = self._spawn(ts)
            events.append(LineEvent(ts, p.product_id, SPAWN, p.x))
            events.extend(self._advance(p, ts, t1))
            self._next_spawn_time = ts + self.config.spawn_interval

        self.time = t1
        events.sort(key=lambda e: (e.time, e.product_id))
        return events

    # -- internals --------------------------------------------------------

    def _spawn(self, t: float) -> Product:
        is_defect = self._rng.random() < self.config.defect_rate
        p = self.tracker.spawn(DEFECT if is_defect else GOOD, "color" if is_defect else None,
                               L.SPAWN_X, t)
        self.tracker.transition(p.product_id, ProductState.MOVING)
        self._spawned += 1
        return p

    def _spawn_clear_time(self, t1: float) -> Optional[float]:
        """Earliest time in this step when the spawn area was clear, or None if still blocked.

        Positions are already advanced to t1, so the nearest product's clearance at t1
        is rolled back to find when it first reached min_gap.
        """
        on_belt = self.tracker.on_belt()
        if not on_belt:
            return float("-inf")
        clearance = min(p.x for p in on_belt) - L.SPAWN_X - self.config.min_gap
        if clearance < 0:
            return None
        if self.config.speed == 0:
            return float("-inf")
        return t1 - clearance / self.config.speed

    def _advance(self, p: Product, t_start: float, t_end: float) -> List[LineEvent]:
        speed = self.config.speed
        x0 = p.x
        x1 = x0 + speed * (t_end - t_start)
        events: List[LineEvent] = []

        def crossed(line: float) -> bool:
            return x0 < line <= x1

        def t_at(line: float) -> float:
            return t_start + (line - x0) / speed

        for name, sx in self.config.stations:
            if p.state in (ProductState.MOVING, ProductState.INSPECTED, ProductState.SORTED) and crossed(sx):
                events.append(LineEvent(t_at(sx), p.product_id, STATION, sx, name))

        if p.state == ProductState.MOVING and crossed(L.INSPECTION_X):
            self.tracker.transition(p.product_id, ProductState.INSPECTED)
            p.inspected_time = t_at(L.INSPECTION_X)
            events.append(LineEvent(p.inspected_time, p.product_id, INSPECT, L.INSPECTION_X))

        if p.state == ProductState.INSPECTED and crossed(L.REJECT_X):
            t = t_at(L.REJECT_X)
            p.sort_time, p.sort_speed = t, speed
            if self.reject_decider(p):
                self.tracker.transition(p.product_id, ProductState.REJECTED)
                events.append(LineEvent(t, p.product_id, REJECT, L.REJECT_X))
                self._exit(p, t, "reject", L.REJECT_X, events)
                return events
            self.tracker.transition(p.product_id, ProductState.SORTED)
            events.append(LineEvent(t, p.product_id, SORT, L.REJECT_X))

        if p.state == ProductState.SORTED and crossed(L.EXIT_X):
            self._exit(p, t_at(L.EXIT_X), "pass", L.EXIT_X, events)
            return events

        p.x = x1
        return events

    def _exit(self, p: Product, t: float, route: str, x: float, events: List[LineEvent]) -> None:
        p.x = x
        p.exit_time = t
        p.exit_route = route
        self.tracker.transition(p.product_id, ProductState.EXITED)
        events.append(LineEvent(t, p.product_id, EXIT, x))
