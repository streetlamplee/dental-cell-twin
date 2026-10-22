"""Per-run event log (events.csv): one row per line event and per vision verdict, in the
order they happen. Used to audit a run afterwards (missing events, timing, queue).
"""

import csv
import os

FIELDS = ["sim_time_s", "product_id", "event", "x", "station", "detail"]


class EventLog:
    def __init__(self, run_dir: str) -> None:
        self.path = os.path.join(run_dir, "events.csv")
        self._f = open(self.path, "w", newline="", encoding="utf-8")
        self._w = csv.writer(self._f)
        self._w.writerow(FIELDS)

    def write(self, sim_time: float, product_id: int, event: str, x: float = None,
              station: str = "", detail: str = "") -> None:
        self._w.writerow([round(sim_time, 4), product_id, event,
                          "" if x is None else round(x, 4), station, detail])

    def close(self) -> None:
        if self._f:
            self._f.close()
            self._f = None


def check_events(rows) -> list:
    """Audit an events.csv (list of dicts). Returns a list of problems (empty = consistent):
    every spawned product must end with exactly one EXIT, LOAD/UNLOAD must pair up, and
    every INSPECT must be followed by exactly one VISION verdict."""
    problems = []
    by_pid = {}
    for r in rows:
        by_pid.setdefault(r["product_id"], []).append(r["event"])
    for pid, evs in by_pid.items():
        if evs.count("SPAWN") != 1:
            problems.append(f"product {pid}: {evs.count('SPAWN')} SPAWN")
        if evs.count("EXIT") != 1:
            problems.append(f"product {pid}: {evs.count('EXIT')} EXIT")
        if evs.count("LOAD") != evs.count("UNLOAD"):
            problems.append(f"product {pid}: LOAD {evs.count('LOAD')} != UNLOAD {evs.count('UNLOAD')}")
        if evs.count("INSPECT") != evs.count("VISION"):
            problems.append(f"product {pid}: INSPECT {evs.count('INSPECT')} != VISION {evs.count('VISION')}")
    return problems
