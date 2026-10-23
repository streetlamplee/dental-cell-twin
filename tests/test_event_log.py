import csv

from core.conveyor import ConveyorConfig, ConveyorSim, INSPECT, ProcessStation
from core.event_log import EventLog, check_events


def test_event_log_round_trip_and_audit(tmp_path):
    sim = ConveyorSim(ConveyorConfig(max_products=6, spawn_interval=2.0,
                                     process=ProcessStation("mill", -1.9, -1.7, 3.0)))
    log = EventLog(str(tmp_path))
    sim.start()
    while not sim.finished:
        for e in sim.step(1 / 60):
            log.write(e.time, e.product_id, e.kind, e.x, e.station)
            if e.kind == INSPECT:
                log.write(e.time, e.product_id, "VISION", detail="good")
    log.close()
    with open(tmp_path / "events.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert check_events(rows) == []
    assert {r["event"] for r in rows} >= {"SPAWN", "LOAD", "UNLOAD", "INSPECT", "VISION", "EXIT"}


def test_audit_finds_missing_verdict_and_exit():
    rows = [{"product_id": "1", "event": e} for e in ("SPAWN", "INSPECT")]
    problems = check_events(rows)
    assert any("EXIT" in p for p in problems) and any("VISION" in p for p in problems)


def test_audit_flags_products_with_missing_views():
    rows = [{"product_id": pid, "event": e} for pid, evs in
            (("1", ("SPAWN", "LOAD", "VIEW", "VIEW", "UNLOAD", "EXIT")), ("2", ("SPAWN", "LOAD", "VIEW", "UNLOAD", "EXIT")))
            for e in evs]
    assert any("VIEW counts" in p for p in check_events(rows))


def test_product_rows_prefer_combined_rows():
    from core.inspection_log import product_rows

    rows = [{"product_id": "1", "view": v} for v in ("0", "1", "all")]
    assert product_rows(rows) == [{"product_id": "1", "view": "all"}]
    assert product_rows([{"product_id": "1"}]) == [{"product_id": "1"}]  # runs before the view column
