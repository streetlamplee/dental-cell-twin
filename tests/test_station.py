"""Processing station (dental mill line): load -> cycle -> unload, queueing, accumulation."""

import pytest

from core.conveyor import (EXIT, INSPECT, LOAD, REJECT, SORT, SPAWN, UNLOAD, ConveyorConfig, ConveyorSim,
                           ProcessStation)
from core.product_tracker import ProductState

MILL = ProcessStation("mill", x_entry=-1.9, x_exit=-1.7, cycle_s=3.0)


def run(cfg, dt=1 / 60, limit=3600):
    sim = ConveyorSim(cfg)
    sim.start()
    events, gaps_ok = [], True
    while not sim.finished:
        events += sim.step(dt)
        # Gaps hold within each belt section; the station separates upstream (unprocessed)
        # from downstream (processed) products.
        for processed in (False, True):
            xs = sorted(p.x for p in sim.tracker.on_belt() if (p.unload_time is not None) == processed)
            gaps_ok &= all(b - a >= cfg.min_gap - 1e-9 for a, b in zip(xs, xs[1:]))
        assert sim.time < limit
    return sim, events, gaps_ok


def by_product(events):
    out = {}
    for e in events:
        out.setdefault(e.product_id, []).append(e)
    return out


def test_every_product_is_processed_once_in_order():
    sim, events, gaps_ok = run(ConveyorConfig(max_products=12, spawn_interval=2.0, process=MILL))
    assert gaps_ok
    for pid, evs in by_product(events).items():
        kinds = [e.kind for e in evs]
        assert kinds in ([SPAWN, LOAD, UNLOAD, INSPECT, SORT, EXIT], [SPAWN, LOAD, UNLOAD, INSPECT, REJECT, EXIT]), (pid, kinds)
    assert all(p.state == ProductState.EXITED for p in sim.tracker.all())


def test_station_holds_one_product_for_at_least_the_cycle_fifo():
    sim, events, _ = run(ConveyorConfig(max_products=12, spawn_interval=2.0, process=MILL))
    ps = sorted(sim.tracker.all(), key=lambda p: p.load_time)
    assert [p.product_id for p in ps] == sorted(p.product_id for p in ps)  # FIFO
    for a, b in zip(ps, ps[1:]):
        assert a.unload_time - a.load_time >= MILL.cycle_s - 1e-9
        assert b.load_time >= a.unload_time - 1e-9  # never two products inside


def test_queue_forms_when_arrivals_exceed_capacity():
    sim, _, gaps_ok = run(ConveyorConfig(max_products=12, spawn_interval=1.0, process=MILL))
    assert gaps_ok
    assert sim.queue_max >= 2
    assert sim.station_utilization > 0.7


def test_no_queue_and_expected_utilization_when_capacity_is_enough():
    sim, _, _ = run(ConveyorConfig(max_products=12, spawn_interval=5.0, process=MILL))
    assert sim.queue_max == 0
    busy = 12 * MILL.cycle_s
    assert sim.station_busy_time == pytest.approx(busy, abs=12 * (1 / 60) + 1e-9)


def test_blocked_exit_waits_inside_and_keeps_gaps():
    cfg = ConveyorConfig(max_products=4, spawn_interval=0.1, speed=0.05,
                         process=ProcessStation("mill", -2.7, -2.6, 0.2))
    sim, events, gaps_ok = run(cfg)
    assert gaps_ok
    assert sim.station_blocked_time > 0
    assert sorted(e.product_id for e in events if e.kind == UNLOAD) == [1, 2, 3, 4]


def test_load_times_do_not_depend_on_dt():
    cfg = dict(max_products=8, spawn_interval=1.5, process=MILL)
    fine, _, _ = run(ConveyorConfig(**cfg), dt=1 / 240)
    coarse, _, _ = run(ConveyorConfig(**cfg), dt=1 / 30)
    for a, b in zip(sorted(fine.tracker.all(), key=lambda p: p.product_id),
                    sorted(coarse.tracker.all(), key=lambda p: p.product_id)):
        assert a.load_time == pytest.approx(b.load_time, abs=1 / 30 + 1e-6)
