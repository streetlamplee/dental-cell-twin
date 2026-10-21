"""Calibrate the color inspector from a calibration run (golden samples).

Uses frames whose ground truth is "good" from a run recorded with a seed that is NOT
used for evaluation. Inside the run's ROI, the product blob is found with a permissive
saturation threshold, then:
  reference_hue = circular mean hue of good products
  sat_min       = 60% of the 5th-percentile product saturation (good and defect frames),
                  but at least 25, so washed-out products still count as foreground
Writes config/inspector.json (ROI is left to the camera model at runtime).

Usage: python scripts/calibrate_inspector.py <calibration_run_dir> [--out config/inspector.json]
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/extensions/visiontwin.factory/visiontwin/factory"))

from core.vision_inspector import InspectorConfig, circular_mean_hue  # noqa: E402

PERMISSIVE_SAT = 25


def product_pixels(rgb, roi, val_min):
    x0, y0, x1, y1 = roi
    hsv = cv2.cvtColor(rgb[y0:y1, x0:x1], cv2.COLOR_RGB2HSV)
    mask = ((hsv[:, :, 1] >= PERMISSIVE_SAT) & (hsv[:, :, 2] >= val_min)).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return None
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return hsv[labels == idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--out", default=str(ROOT / "config" / "inspector.json"))
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    base = InspectorConfig(**run["inspector"])
    roi = tuple(base.roi)

    with open(run_dir / "inspections.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    good_hues, sats, missing = [], [], 0
    for row in rows:
        bgr = cv2.imread(str(run_dir / row["frame_file"]))
        px = product_pixels(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), roi, base.val_min)
        if px is None:
            missing += 1
            continue
        sats.append(np.percentile(px[:, 1], 5))
        if row["ground_truth"] == "good":
            good_hues.append(px[:, 0])

    if not good_hues:
        print("No good-product frames with a detectable blob; cannot calibrate.")
        return 1

    ref = circular_mean_hue(np.concatenate(good_hues))
    sat_min = int(max(PERMISSIVE_SAT, 0.6 * min(sats)))
    cfg = InspectorConfig(roi=None, sat_min=sat_min, val_min=base.val_min, min_area_px=base.min_area_px,
                          reference_hue=round(ref, 2), hue_tolerance=base.hue_tolerance,
                          good_ratio_min=base.good_ratio_min)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    cfg.save(args.out)
    print(f"calibration run: {run_dir.name}  frames={len(rows)}  good_used={len(good_hues)}  no_blob={missing}")
    print(f"product saturation p5 per frame: min={min(sats):.0f} median={np.median(sats):.0f}")
    print(f"reference_hue={cfg.reference_hue}  sat_min={cfg.sat_min}  -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
