"""Calibrate the inspector from a calibration run (golden samples).

Uses frames whose ground truth is "good" from a run recorded with a seed that is NOT
used for evaluation. Inside the run's ROI, the product blob is found with a permissive
saturation threshold, then:
  reference_hue = circular mean hue of good products
  sat_min       = 60% of the 5th-percentile product saturation (all frames), >= 25
For CAD parts (run.json "part" != "box") also, from the good frames only:
  good_ratio_min      = 80% of the lowest good hue-match score
  interior_bright_min = 50% of the lowest good interior-bright fraction (shape check on)
Defect frames are only printed for information; thresholds come from golden samples.
Writes config/inspector.json (box) or config/inspector_<part>.json (ROI is left to the
camera model at runtime).

Usage: python scripts/calibrate_inspector.py <calibration_run_dir>
"""

import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/extensions/visiontwin.factory/visiontwin/factory"))

from core.vision_inspector import InspectorConfig, VisionInspector, circular_mean_hue  # noqa: E402

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
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    run_dir = Path(sys.argv[1])
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    part = run.get("part", "box")
    base = InspectorConfig(**run["inspector"])
    roi = tuple(base.roi)
    out = ROOT / "config" / ("inspector.json" if part == "box" else f"inspector_{part}.json")

    with open(run_dir / "inspections.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    results = run_dir / "results.csv"
    if results.exists():  # ground-truth defect kind lives in results.csv
        with open(results, encoding="utf-8") as f:
            kinds = {r["product_id"]: r.get("defect_kind", "") for r in csv.DictReader(f)}
        for r in rows:
            r["defect_kind"] = kinds.get(r["product_id"], "")
    frames = [(r, cv2.cvtColor(cv2.imread(str(run_dir / r["frame_file"])), cv2.COLOR_BGR2RGB)) for r in rows]

    good_hues, sats, missing = [], [], 0
    for row, rgb in frames:
        px = product_pixels(rgb, roi, base.val_min)
        if px is None:
            missing += 1
            continue
        sats.append(np.percentile(px[:, 1], 5))
        if row["ground_truth"] == "good":
            good_hues.append(px[:, 0])
    if not good_hues:
        print("No good-product frames with a detectable blob; cannot calibrate.")
        return 1

    cfg = InspectorConfig(roi=None, sat_min=int(max(PERMISSIVE_SAT, 0.6 * min(sats))), val_min=base.val_min,
                          min_area_px=base.min_area_px,
                          reference_hue=round(circular_mean_hue(np.concatenate(good_hues)), 2),
                          hue_tolerance=base.hue_tolerance, good_ratio_min=base.good_ratio_min)
    print(f"calibration run: {run_dir.name} part={part} frames={len(rows)} good_used={len(good_hues)} no_blob={missing}")
    print(f"product saturation p5 per frame: min={min(sats):.0f} median={np.median(sats):.0f}")

    if part != "box":
        probe = InspectorConfig(**{**cfg.__dict__, "roi": roi, "good_ratio_min": 0.0, "interior_bright_min": 0.0})
        insp = VisionInspector(probe)
        stats = {}
        for row, rgb in frames:
            r = insp.inspect(rgb)
            key = row["ground_truth"] if row["ground_truth"] == "good" else f"defect:{row.get('defect_kind') or '?'}"
            stats.setdefault(key, []).append((r.score, r.interior_bright))
        for key, vals in sorted(stats.items()):
            s, b = np.array(vals).T
            print(f"  {key:16s} n={len(vals):2d} score min/med/max={s.min():.2f}/{np.median(s):.2f}/{s.max():.2f} "
                  f"interior_bright min/med/max={b.min():.2f}/{np.median(b):.2f}/{b.max():.2f}")
        good = np.array(stats["good"])
        cfg.good_ratio_min = round(float(0.8 * good[:, 0].min()), 3)
        cfg.interior_bright_min = round(float(0.5 * good[:, 1].min()), 3)

    out.parent.mkdir(parents=True, exist_ok=True)
    cfg.save(str(out))
    print(f"reference_hue={cfg.reference_hue} sat_min={cfg.sat_min} good_ratio_min={cfg.good_ratio_min} "
          f"interior_bright_min={cfg.interior_bright_min} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
