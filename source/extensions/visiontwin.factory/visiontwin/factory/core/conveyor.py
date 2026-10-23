"""Time-stepped conveyor simulation.

Positions advance by simulation time `dt`, not by render frames, and line
crossings are detected on the segment [x_before, x_after], so a large dt
cannot skip an inspection or reject line.

Optional processing station: unprocessed products stop at the station entry; when the
station is free the product is loaded (PROCESSING, off the belt), released after `cycle_s`
at the exit when the exit is clear, and continues as MOVING. While the station is busy,
products queue at the entry and the ones behind stop at `min_gap` (accumulating conveyor).

Inspection cell (station with `inspects=True`, dental crown line): the station itself takes
the pictures. It emits a VIEW event at `load + view_times[k]` for every view and, on unload,
the product leaves as INSPECTED (INSPECT event at the exit), so no inspection line follows.
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
STATION = "STATION"  # crossed a (visual) station line; `station` names it
LOAD = "LOAD"  # loaded into the processing station
UNLOAD = "UNLOAD"  # processed and put back on the belt
VIEW = "VIEW"  # inspection cell: take view `index` of the product in the station now


@dataclass(frozen=True)
class LineEvent:
    time: float
    product_id: int
    kind: str
    x: float
    station: str = ""
    index: int = -1  # VIEW: view number


@dataclass(frozen=True)
class ProcessStation:
    name: str
    x_entry: float
    x_exit: float
    cycle_s: float
    view_times: Tuple[float, ...] = ()  # seconds after LOAD at which VIEW events fire
    inspects: bool = False  # True: the station is the inspection (product leaves INSPECTED)


@dataclass
class ConveyorConfig:
    seed: int = 42
    speed: float = 0.5  # m/s
    spawn_interval: float = 1.5  # s
    defect_rate: float = 0.3
    max_products: int = 30
    min_gap: float = L.PRODUCT_SIZE * 1.5  # spawn waits until the previous product moved this far
    stations: Tuple[Tuple[str, float], ...] = ()  # (name, x): visual stations, emit STATION events
    # Defect kinds drawn uniformly for defective products. With a single kind no extra random
    # number is drawn, so box runs keep exactly the same ground-truth sequence as before.
    defect_kinds: Tuple[str, ...] = ("color",)
    process: Optional[ProcessStation] = None


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
        # processing station state + line metrics
        self.station_product: Optional[int] = None
        self._station_done = 0.0
        self._station_free_at = 0.0
        self.station_busy_time = 0.0
        self.station_blocked_time = 0.0
        self.queue_len = 0
        self.queue_max = 0
        self._queue_area = 0.0  # integral of queue length over time

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
        return (self._spawned >= self.config.max_products and not self.tracker.on_belt()
                and self.station_product is None)

    @property
    def queue_mean(self) -> float:
        return self._queue_area / self.time if self.time > 0 else 0.0

    @property
    def station_utilization(self) -> float:
        return self.station_busy_time / self.time if self.time > 0 else 0.0

    def step(self, dt: float) -> List[LineEvent]:
        """Advance the simulation by dt seconds and return events in time order."""
        if not self.running or dt <= 0:
            return []
        t0, t1 = self.time, self.time + dt
        events: List[LineEvent] = []

        if self.config.process is not None:
            self._station_unload(t0, t1, events)

        # Move products already on the belt during [t0, t1], downstream first so that each
        # product's leader has already moved (accumulation needs the leader's new position).
        leader_x = None
        waiting = 0
        for p in sorted(self.tracker.on_belt(), key=lambda p: -p.x):
            evs, leader_x, stopped = self._advance(p, t0, t1, leader_x)
            events.extend(evs)
            waiting += stopped

        # Spawn products scheduled inside this step, then move them for the remaining time.
        while self._spawned < self.config.max_products and self._next_spawn_time <= t1:
            t_clear = self._spawn_clear_time(t1)
            if t_clear is None:
                break  # retry next step; schedule slips instead of overlapping products
            ts = max(self._next_spawn_time, t0, t_clear)
            p = self._spawn(ts)
            events.append(LineEvent(ts, p.product_id, SPAWN, p.x))
            evs, _, _ = self._advance(p, ts, t1, None)
            events.extend(evs)
            self._next_spawn_time = ts + self.config.spawn_interval

        if self.config.process is not None:
            self._station_views(t0, t1, events)
            if self.station_product is not None:
                self.station_busy_time += dt
            self.queue_len = waiting
            self.queue_max = max(self.queue_max, waiting)
            self._queue_area += waiting * dt

        self.time = t1
        events.sort(key=lambda e: (e.time, e.product_id))
        return events

    # -- internals --------------------------------------------------------

    def _spawn(self, t: float) -> Product:
        is_defect = self._rng.random() < self.config.defect_rate
        kind = None
        if is_defect:
            kinds = self.config.defect_kinds
            kind = kinds[0] if len(kinds) == 1 else kinds[self._rng.randrange(len(kinds))]
        p = self.tracker.spawn(DEFECT if is_defect else GOOD, kind, L.SPAWN_X, t)
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

    def _station_views(self, t0: float, t1: float, events: List[LineEvent]) -> None:
        st = self.config.process
        if self.station_product is None:
            return
        p = self.tracker.get(self.station_product)
        for k, vt in enumerate(st.view_times):
            t = p.load_time + vt
            if t0 < t <= t1:
                events.append(LineEvent(t, p.product_id, VIEW, st.x_entry, st.name, k))

    def _station_unload(self, t0: float, t1: float, events: List[LineEvent]) -> None:
        st = self.config.process
        if self.station_product is None or self._station_done > t1:
            return
        gap = self.config.min_gap
        # Only processed products (downstream of the station) can block the exit. Unprocessed
        # products wait at the entry and never move into it; counting them deadlocked the line
        # (queue waits for the station, station waits for the queue).
        if any(q.unload_time is not None and abs(q.x - st.x_exit) < gap for q in self.tracker.on_belt()):
            self.station_blocked_time += t1 - max(t0, self._station_done)  # exit blocked: wait inside
            return
        t = max(self._station_done, t0)
        p = self.tracker.get(self.station_product)
        p.x, p.unload_time = st.x_exit, t
        self.station_product = None
        self._station_free_at = t
        events.append(LineEvent(t, p.product_id, UNLOAD, st.x_exit, st.name))
        if st.inspects:
            self.tracker.transition(p.product_id, ProductState.INSPECTED)
            p.inspected_time = t
            events.append(LineEvent(t, p.product_id, INSPECT, st.x_exit, st.name))
        else:
            self.tracker.transition(p.product_id, ProductState.MOVING)

    def _station_load(self, p: Product, t: float, events: List[LineEvent]) -> None:
        st = self.config.process
        self.tracker.transition(p.product_id, ProductState.PROCESSING)
        p.x, p.load_time = st.x_entry, t
        self.station_product = p.product_id
        self._station_done = t + st.cycle_s
        events.append(LineEvent(t, p.product_id, LOAD, st.x_entry, st.name))

    def _advance(self, p: Product, t_start: float, t_end: float, leader_x: Optional[float]):
        """Move one product. Returns (events, x to use as the next product's leader, stopped)."""
        speed = self.config.speed
        st = self.config.process
        x0 = p.x
        x_free = x0 + speed * (t_end - t_start)
        x1 = x_free
        events: List[LineEvent] = []
        if st is not None:
            if leader_x is not None:
                x1 = min(x1, leader_x - self.config.min_gap)  # accumulate behind the leader
            unprocessed = p.state == ProductState.MOVING and p.unload_time is None
            if unprocessed and x0 <= st.x_entry:
                x1 = min(x1, st.x_entry)  # stop at the entry until the station takes it
            x1 = max(x1, x0)  # never move backwards
            if unprocessed and x1 >= st.x_entry and self.station_product is None:
                t_arrive = t_start + (st.x_entry - x0) / speed if speed > 0 and x0 < st.x_entry else t_start
                self._station_load(p, max(t_arrive, self._station_free_at, t_start), events)
                return events, leader_x, False
        stopped = st is not None and x1 < x_free - 1e-12 and p.unload_time is None

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
                return events, leader_x, stopped
            self.tracker.transition(p.product_id, ProductState.SORTED)
            events.append(LineEvent(t, p.product_id, SORT, L.REJECT_X))

        if p.state == ProductState.SORTED and crossed(L.EXIT_X):
            self._exit(p, t_at(L.EXIT_X), "pass", L.EXIT_X, events)
            return events, leader_x, stopped

        p.x = x1
        return events, x1, stopped

    def _exit(self, p: Product, t: float, route: str, x: float, events: List[LineEvent]) -> None:
        p.x = x
        p.exit_time = t
        p.exit_route = route
        self.tracker.transition(p.product_id, ProductState.EXITED)
        events.append(LineEvent(t, p.product_id, EXIT, x))
