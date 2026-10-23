"""Per-run inspection records: one CSV row per inspected product, plus its frame PNG.
Inspection cell (several views): one row per view (view = 0, 1, ...) and one combined row
(view = "all") per product; product-level analysis uses the "all" rows when present.

Ground truth is written here for evaluation only; it is copied from the tracker,
never from the inspector, and the inspector never reads this file.
"""

import csv
import os
from dataclasses import asdict, dataclass
from typing import List, Optional

import cv2
import numpy as np

FIELDS = [
    "run_id", "seed", "product_id", "view", "ground_truth", "predicted_label", "defect_reason", "score", "mean_hue",
    "area_px", "interior_ratio", "interior_bright", "capture_latency_ms", "frame_offset", "inspection_latency_ms", "simulation_time_s",
    "conveyor_speed", "lighting_condition", "frame_file", "reason",
]


@dataclass
class InspectionRecord:
    run_id: str
    seed: int
    product_id: int
    ground_truth: str
    predicted_label: str
    defect_reason: str
    score: float
    mean_hue: float
    area_px: int
    interior_ratio: object  # float, "" when the shape check is off
    interior_bright: object
    capture_latency_ms: float
    frame_offset: object  # captured SWH frame - trigger frame (0 = exact); "" if unknown
    inspection_latency_ms: float
    simulation_time_s: float
    conveyor_speed: float
    lighting_condition: str
    frame_file: str
    reason: str
    view: object = 0  # view index, or "all" for the combined verdict of a multi-view product


class InspectionLog:
    def __init__(self, run_dir: str, record_frames: bool = True) -> None:
        self.run_dir = run_dir
        self.frames_dir = os.path.join(run_dir, "frames")
        self.csv_path = os.path.join(run_dir, "inspections.csv")
        self.record_frames = record_frames
        os.makedirs(self.frames_dir, exist_ok=True)
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, FIELDS).writeheader()

    def save_frame(self, product_id: int, rgb: np.ndarray, view: Optional[int] = None) -> Optional[str]:
        if not self.record_frames:
            return None
        name = f"P_{product_id:04d}.png" if view is None else f"P_{product_id:04d}_v{view}.png"
        cv2.imwrite(os.path.join(self.frames_dir, name), cv2.cvtColor(rgb[:, :, :3], cv2.COLOR_RGB2BGR))
        return f"frames/{name}"

    def append(self, record: InspectionRecord) -> None:
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, FIELDS).writerow(asdict(record))


def product_rows(rows: List[dict]) -> List[dict]:
    """Product-level rows of an inspections.csv: the combined "all" rows of a multi-view run,
    else the single-view rows (older runs have no view column)."""
    combined = [r for r in rows if str(r.get("view", "")) == "all"]
    return combined if combined else [r for r in rows if str(r.get("view", "0")) in ("0", "")]
