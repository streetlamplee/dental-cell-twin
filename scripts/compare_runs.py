"""Reproducibility check: compare two runs' results.csv on the deterministic columns.

With a fixed simulation step the same seed must give the same products, verdicts,
routes and simulation times. Wall-clock columns (inspection_*_ms, latency) are ignored.

Usage: python scripts/compare_runs.py <run_dir_a> <run_dir_b>
Exit code 0 = identical on deterministic columns, 1 = differences (printed).
"""

import csv
import sys
from pathlib import Path

DETERMINISTIC = ["product_id", "ground_truth", "predicted_label", "sort_result", "sort_reason",
                 "sort_correct", "late_prediction", "simulation_time_s", "conveyor_speed", "final_state"]


def load(run_dir):
    with open(Path(run_dir) / "results.csv", encoding="utf-8") as f:
        return {r["product_id"]: r for r in csv.DictReader(f)}


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    a, b = load(sys.argv[1]), load(sys.argv[2])
    diffs = []
    for pid in sorted(set(a) | set(b), key=int):
        if pid not in a or pid not in b:
            diffs.append(f"product {pid}: present in only one run")
            continue
        for col in DETERMINISTIC:
            if a[pid][col] != b[pid][col]:
                diffs.append(f"product {pid} {col}: {a[pid][col]!r} != {b[pid][col]!r}")
    print(f"A: {Path(sys.argv[1]).name} ({len(a)} products)  B: {Path(sys.argv[2]).name} ({len(b)} products)")
    print(f"compared columns: {', '.join(DETERMINISTIC)}")
    if diffs:
        print(f"DIFFERENT: {len(diffs)} differences")
        for d in diffs[:50]:
            print("  " + d)
        return 1
    print("IDENTICAL on all deterministic columns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
