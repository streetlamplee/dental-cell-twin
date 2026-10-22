"""Per-product run results (results.csv): one row per product joining tracker state,
vision verdict and the reject-line decision. Contains the plan's required fields.
"""

import csv
from typing import Dict, Iterable, List

from .sorting import SortDecision, SortingController

FIELDS = [
    "run_id", "seed", "product_id", "ground_truth", "defect_kind", "predicted_label", "defect_reason", "score",
    "inspection_start_ms", "inspection_end_ms", "inspection_latency_ms",
    "sort_result", "sort_reason", "sort_correct", "late_prediction",
    "simulation_time_s", "conveyor_speed", "lighting_condition", "final_state",
]


def _r(x, digits=3):
    return "" if x is None else round(x, digits)


def build_rows(run_id: str, seed: int, lighting: str, products: Iterable,
               decisions: Dict[int, SortDecision]) -> List[dict]:
    rows = []
    for p in sorted(products, key=lambda p: p.product_id):
        d = decisions.get(p.product_id)
        latency = (None if p.inspection_start_ms is None or p.inspection_end_ms is None
                   else p.inspection_end_ms - p.inspection_start_ms)
        rows.append({
            "run_id": run_id, "seed": seed, "product_id": p.product_id,
            "ground_truth": p.ground_truth,
            "defect_kind": p.defect_kind or "",
            "predicted_label": "" if d is None or d.prediction is None else d.prediction,
            "defect_reason": p.defect_reason or "",
            "score": _r(p.score, 4),
            "inspection_start_ms": _r(p.inspection_start_ms, 2),
            "inspection_end_ms": _r(p.inspection_end_ms, 2),
            "inspection_latency_ms": _r(latency, 2),
            "sort_result": "" if d is None else d.route,
            "sort_reason": "" if d is None else d.reason,
            "sort_correct": "" if d is None else SortingController.route_correct(p.ground_truth, d.route),
            "late_prediction": p.late_prediction or "",
            "simulation_time_s": _r(p.sort_time),
            "conveyor_speed": _r(p.sort_speed),
            "lighting_condition": lighting,
            "final_state": p.state.value,
        })
    return rows


def write_csv(path: str, rows: List[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows)
