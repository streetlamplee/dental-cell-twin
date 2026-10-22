"""Audit a recorded run (system Python): events.csv consistency + summary.json counters.

Checks every product has exactly one SPAWN and one EXIT, LOAD/UNLOAD pairs, one VISION
verdict per INSPECT, and that summary.json reports no unfinished/pending products.

Usage: python scripts/check_run.py <run_dir>   (exit code 1 on problems)
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/extensions/visiontwin.factory/visiontwin/factory"))

from core.event_log import check_events  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    run = Path(sys.argv[1])
    with open(run / "events.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    problems = check_events(rows)
    for key in ("not_exited", "pending_frames_at_finalize", "frame_mismatches", "capture_timeouts"):
        if summary.get(key):
            problems.append(f"summary {key} = {summary[key]}")
    counts = {}
    for r in rows:
        counts[r["event"]] = counts.get(r["event"], 0) + 1
    print(f"run {run.name}: {len({r['product_id'] for r in rows})} products, {len(rows)} events "
          f"({', '.join(f'{k}={v}' for k, v in sorted(counts.items()))}), sim {summary.get('simulation_time_s')} s")
    if problems:
        print(f"PROBLEMS ({len(problems)}):")
        for p in problems:
            print("  " + p)
        return 1
    print("OK: every product spawned once, processed/inspected consistently and left the line")
    return 0


if __name__ == "__main__":
    sys.exit(main())
