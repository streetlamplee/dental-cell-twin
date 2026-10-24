"""Day 4: inspection verdict -> reject-line decision, keyed by product ID.

The harness delivers verdicts asynchronously `latency_s` (simulation seconds) after the
inspection-line crossing, like the Kit frame callback. `verdict_fn` stands in for the
camera + inspector (it is a test oracle, not the real inspector).
"""

import pytest

from core import layout as L
from core.conveyor import INSPECT, ConveyorConfig, ConveyorSim
from core.product_tracker import DEFECT, GOOD, ProductState
from core.run_results import FIELDS, build_rows
from core.sorting import PASS, REJECT, SortingController

DT = 1 / 60
TRAVEL = L.REJECT_X - L.INSPECTION_X  # metres between the two lines


def run_line(cfg, latency_s, verdict_fn, sorter=None, speed_at=None):
    sorter = sorter or SortingController()
    sim = ConveyorSim(cfg, reject_decider=sorter.decide)
    pending = []  # (due_time, product_id)
    speed_at = dict(speed_at or {})
    def deliver(until):
        for due, pid in sorted(x for x in pending if x[0] <= until):
            pending.remove((due, pid))
            p = sim.tracker.get(pid)
            verdict = verdict_fn(p)
            if sorter.is_sorted(pid):
                p.late_prediction = verdict
                sorter.record_late(pid)
            else:
                p.prediction = verdict

    sim.start()
    while not sim.finished:
        for t_change in [t for t in speed_at if t <= sim.time]:
            sim.set_speed(speed_at.pop(t_change))
        deliver(sim.time)
        for e in sim.step(DT):
            if e.kind == INSPECT:
                pending.append((e.time + latency_s, e.product_id))
        assert sim.time < 3600
    deliver(float("inf"))  # the line can finish before the last verdicts arrive
    return sim, sorter


def perfect(p):
    return p.ground_truth


def test_perfect_vision_sorts_every_product_correctly():
    sim, sorter = run_line(ConveyorConfig(max_products=30), 0.1, perfect)
    products = sim.tracker.all()
    assert len(sorter.decisions) == 30
    for p in products:
        d = sorter.decisions[p.product_id]
        assert d.route == (REJECT if p.ground_truth == DEFECT else PASS)
        assert p.exit_route == d.route
        assert p.state == ProductState.EXITED
    assert sorter.late_results == []


def test_verdict_is_applied_to_its_own_product_only():
    # Verdict depends only on the product id (odd -> defect), not on ground truth:
    # every decision must follow its own id, proving there is no cross-product mix-up.
    sim, sorter = run_line(ConveyorConfig(max_products=30), 0.3,
                           lambda p: DEFECT if p.product_id % 2 else GOOD)
    for pid, d in sorter.decisions.items():
        assert d.route == (REJECT if pid % 2 else PASS), pid


def test_result_slower_than_travel_time_is_fail_safe_and_late():
    travel_time = TRAVEL / ConveyorConfig().speed
    sim, sorter = run_line(ConveyorConfig(max_products=10), travel_time + 1.0, perfect)
    assert all(d.route == REJECT and d.prediction is None for d in sorter.decisions.values())
    assert all("no result" in d.reason for d in sorter.decisions.values())
    assert sorted(sorter.late_results) == list(range(1, 11))
    assert all(p.late_prediction == p.ground_truth for p in sim.tracker.all())


def test_unknown_prediction_follows_policy():
    sim, sorter = run_line(ConveyorConfig(max_products=5), 0.1, lambda p: "unknown")
    assert all(d.route == REJECT and "unknown" in d.reason for d in sorter.decisions.values())
    sim, sorter = run_line(ConveyorConfig(max_products=5), 0.1, lambda p: "unknown",
                           sorter=SortingController(unknown_policy=PASS))
    assert all(d.route == PASS for d in sorter.decisions.values())
    with pytest.raises(ValueError):
        SortingController(unknown_policy="maybe")


def test_speed_up_mid_run_keeps_ids_and_shrinks_the_result_deadline():
    # At 2 m/s the inspection->reject travel takes 1 s. A 0.5 s verdict still makes it,
    # a 1.5 s verdict does not (those products go to the fail-safe route).
    cfg = ConveyorConfig(max_products=30)
    sim, sorter = run_line(cfg, 0.5, perfect, speed_at={10.0: 2.0})
    assert all(sorter.route_correct(p.ground_truth, sorter.decisions[p.product_id].route)
               for p in sim.tracker.all())

    sim, sorter = run_line(ConveyorConfig(max_products=30), 1.5, perfect, speed_at={10.0: 2.0})
    fast = [p for p in sim.tracker.all() if p.sort_speed == 2.0 and p.inspected_time >= 10.0]
    assert fast, "expected products inspected after the speed change"
    assert all(sorter.decisions[p.product_id].prediction is None for p in fast)
    slow = [p for p in sim.tracker.all() if p.sort_speed == 0.5]
    assert all(sorter.decisions[p.product_id].prediction == p.ground_truth for p in slow)


def test_tight_spacing_keeps_decisions_per_id():
    cfg = ConveyorConfig(max_products=30, spawn_interval=0.05)  # spawns limited by min_gap
    sim, sorter = run_line(cfg, 0.3, perfect)
    assert len(sorter.decisions) == 30
    assert all(sorter.route_correct(p.ground_truth, sorter.decisions[p.product_id].route)
               for p in sim.tracker.all())


def test_product_cannot_be_sorted_twice():
    sorter = SortingController()
    sim = ConveyorSim(ConveyorConfig(max_products=1))
    p = sim.tracker.spawn(GOOD, None, 0.0, 0.0)
    sorter.decide(p)
    with pytest.raises(RuntimeError):
        sorter.decide(p)


def test_results_rows_contain_plan_fields_and_correctness():
    sim, sorter = run_line(ConveyorConfig(max_products=6), 0.1,
                           lambda p: GOOD)  # every defect is missed on purpose
    rows = build_rows("r1", 42, "default", sim.tracker.all(), sorter.decisions)
    required = {"run_id", "seed", "product_id", "ground_truth", "predicted_label",
                "inspection_start_ms", "inspection_end_ms", "sort_result",
                "simulation_time_s", "conveyor_speed", "lighting_condition"}
    assert required <= set(FIELDS)
    assert [r["product_id"] for r in rows] == list(range(1, 7))
    for r in rows:
        assert r["sort_result"] == PASS
        assert r["sort_correct"] == (r["ground_truth"] == GOOD)


def test_inspection_off_passes_every_product_without_a_verdict():
    sorter = SortingController(inspection=False)
    for pid, pred in ((1, "defect"), (2, None), (3, "unknown")):
        p = type("P", (), {"product_id": pid, "prediction": pred})()
        assert sorter.decide(p) is False
        assert sorter.decisions[pid].route == PASS and sorter.decisions[pid].reason == "no inspection (vision off)"
