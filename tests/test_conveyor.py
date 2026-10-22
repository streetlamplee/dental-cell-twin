import pytest

from core import layout as L
from core.conveyor import EXIT, INSPECT, REJECT, SORT, SPAWN, ConveyorConfig, ConveyorSim
from core.product_tracker import DEFECT, InvalidTransition, ProductState, ProductTracker, GOOD


def run_to_end(sim: ConveyorSim, dt: float, max_time: float = 600.0):
    sim.start()
    events = []
    while not sim.finished:
        events.extend(sim.step(dt))
        assert sim.time < max_time, "simulation did not finish"
    return events


def kinds_by_product(events):
    out = {}
    for e in events:
        out.setdefault(e.product_id, []).append(e.kind)
    return out


def test_30_products_unique_ids_and_complete_lifecycle():
    sim = ConveyorSim(ConveyorConfig(max_products=30))
    events = run_to_end(sim, dt=1 / 60)

    ids = [p.product_id for p in sim.tracker.all()]
    assert len(ids) == 30
    assert len(set(ids)) == 30
    for pid, kinds in kinds_by_product(events).items():
        assert kinds == [SPAWN, INSPECT, SORT, EXIT], f"product {pid}: {kinds}"
    assert all(p.state == ProductState.EXITED for p in sim.tracker.all())


@pytest.mark.parametrize("dt", [1 / 120, 1 / 30, 0.25, 1.0, 10.0])
def test_large_dt_does_not_skip_lines(dt):
    sim = ConveyorSim(ConveyorConfig(max_products=10))
    events = run_to_end(sim, dt=dt)
    for pid, kinds in kinds_by_product(events).items():
        assert kinds == [SPAWN, INSPECT, SORT, EXIT], f"dt={dt} product {pid}: {kinds}"


def test_crossing_time_independent_of_dt():
    fine = ConveyorSim(ConveyorConfig(max_products=5))
    coarse = ConveyorSim(ConveyorConfig(max_products=5))
    ef = [e for e in run_to_end(fine, 1 / 240) if e.kind == INSPECT]
    ec = [e for e in run_to_end(coarse, 0.5) if e.kind == INSPECT]
    assert [e.product_id for e in ef] == [e.product_id for e in ec]
    for a, b in zip(ef, ec):
        assert a.time == pytest.approx(b.time, abs=1e-6)


def test_events_are_time_ordered():
    sim = ConveyorSim(ConveyorConfig(max_products=30))
    events = run_to_end(sim, dt=0.3)
    times = [e.time for e in events]
    assert times == sorted(times)


def test_reject_decider_routes_products():
    sim = ConveyorSim(ConveyorConfig(max_products=30, defect_rate=0.5),
                      reject_decider=lambda p: p.ground_truth == DEFECT)
    events = run_to_end(sim, dt=1 / 60)
    by = kinds_by_product(events)
    for p in sim.tracker.all():
        if p.ground_truth == DEFECT:
            assert by[p.product_id] == [SPAWN, INSPECT, REJECT, EXIT]
            assert p.exit_route == "reject"
            assert p.x == L.REJECT_X
        else:
            assert by[p.product_id] == [SPAWN, INSPECT, SORT, EXIT]
            assert p.exit_route == "pass"


def test_same_seed_same_ground_truth_and_different_seed_differs():
    def labels(seed):
        sim = ConveyorSim(ConveyorConfig(seed=seed, max_products=30))
        run_to_end(sim, dt=0.1)
        return [p.ground_truth for p in sim.tracker.all()]

    assert labels(42) == labels(42)
    assert labels(42) != labels(7)
    assert set(labels(42)) == {GOOD, DEFECT}


def test_stop_freezes_and_speed_change_keeps_events_complete():
    sim = ConveyorSim(ConveyorConfig(max_products=10))
    sim.start()
    events = sim.step(2.0)
    sim.stop()
    xs = [p.x for p in sim.tracker.on_belt()]
    assert sim.step(5.0) == []
    assert [p.x for p in sim.tracker.on_belt()] == xs

    sim.set_speed(1.5)
    events += run_to_end(sim, dt=1 / 60)
    for pid, kinds in kinds_by_product(events).items():
        assert kinds == [SPAWN, INSPECT, SORT, EXIT], f"product {pid}: {kinds}"


def test_zero_speed_does_not_move_or_spawn_overlapping():
    sim = ConveyorSim(ConveyorConfig(max_products=5, spawn_interval=0.1))
    sim.set_speed(0.0)
    sim.start()
    for _ in range(100):
        sim.step(0.1)
    assert len(sim.tracker) == 1  # spawn area stays blocked by the first product


def test_products_never_spawn_closer_than_min_gap():
    cfg = ConveyorConfig(max_products=30, spawn_interval=0.05)  # far too fast on purpose
    sim = ConveyorSim(cfg)
    sim.start()
    while not sim.finished:
        sim.step(1 / 60)
        xs = sorted(p.x for p in sim.tracker.on_belt())
        for a, b in zip(xs, xs[1:]):
            assert b - a >= cfg.min_gap - 1e-9
        assert sim.time < 600


def test_station_line_emits_one_event_per_product_and_keeps_lifecycle():
    cfg = ConveyorConfig(max_products=10, stations=(("mill", -1.8),))
    sim = ConveyorSim(cfg)
    events = run_to_end(sim, dt=0.25)
    station = [e for e in events if e.kind == "STATION"]
    assert [e.product_id for e in station] == list(range(1, 11))
    assert all(e.station == "mill" and e.x == -1.8 for e in station)
    for pid, kinds in kinds_by_product([e for e in events if e.kind != "STATION"]).items():
        assert kinds == [SPAWN, INSPECT, SORT, EXIT]


def test_defect_kinds_split_and_single_kind_keeps_box_sequence():
    base = ConveyorSim(ConveyorConfig(seed=42, max_products=30))
    run_to_end(base, dt=0.25)
    single = ConveyorSim(ConveyorConfig(seed=42, max_products=30, defect_kinds=("color",)))
    run_to_end(single, dt=0.25)
    assert [p.ground_truth for p in base.tracker.all()] == [p.ground_truth for p in single.tracker.all()]

    multi = ConveyorSim(ConveyorConfig(seed=42, max_products=60, defect_rate=0.5,
                                       defect_kinds=("color", "missing")))
    run_to_end(multi, dt=0.25)
    kinds = [p.defect_kind for p in multi.tracker.all() if p.ground_truth == DEFECT]
    assert set(kinds) == {"color", "missing"}
    assert all(p.defect_kind is None for p in multi.tracker.all() if p.ground_truth == GOOD)


def test_invalid_transition_raises():
    t = ProductTracker()
    p = t.spawn(GOOD, None, 0.0, 0.0)
    with pytest.raises(InvalidTransition):
        t.transition(p.product_id, ProductState.EXITED)
    with pytest.raises(ValueError):
        t.spawn("unknown", None, 0.0, 0.0)
