"""Calibrate the inspector from a calibration run (golden samples).

Uses frames whose ground truth is "good" from a run recorded with a seed that is NOT
used for evaluation. Defect frames are only printed for information; every threshold
comes from the golden samples with a margin.

box (default product):
  reference_hue = circular mean hue of good products; sat_min = 60% of the 5th-percentile
  product saturation (all frames), >= 25
CAD parts, per assets/parts/catalog.json "inspection":
  segment "saturation" + color "hue" (kfl08): as box, plus
      good_ratio_min = 80% of the lowest good hue-match score
      interior_check: interior_bright_min = 50% of the lowest good interior-bright fraction
  segment "bright" + color "ab" (dental crown):
      reference_ab = median Lab a*b* of good product pixels
      ab_tolerance = 1.5 x the 90th-percentile pixel distance (>= 6)
      good_ratio_min = 80% of the lowest good ab-match score
  golden_contour: contour of the good sample with the median area;
      shape_dist_max = max(0.02, 2 x largest good distance),
      area_ratio_tol = max(0.05, 2 x largest good |area ratio - 1|)
  silhouette_check: silhouette_diff_max = max(0.02, 2 x largest good silhouette difference)
Writes config/inspector.json (box) or config/inspector_<part>.json (ROI is left to the
camera model at runtime). Inspection cell runs (run.json "views"): every view is calibrated
on its own frames and the file holds {"views": [...]}.

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

from core.inspection_log import product_rows  # noqa: E402
from core.vision_inspector import (InspectorConfig, VisionInspector, circular_mean_hue,  # noqa: E402
                                   save_view_configs, silhouette_diff)

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


def print_stats(title, stats, fields):
    for key, vals in sorted(stats.items()):
        arr = np.array(vals, dtype=float)
        parts = [f"{f} {arr[:, i].min():.3f}/{np.median(arr[:, i]):.3f}/{arr[:, i].max():.3f}"
                 for i, f in enumerate(fields)]
        print(f"  {title} {key:16s} n={len(vals):2d} " + "  ".join(parts))


def load_frames(run_dir: Path, rows):
    return [(r, cv2.cvtColor(cv2.imread(str(run_dir / r["frame_file"])), cv2.COLOR_BGR2RGB)) for r in rows]


def calibrate(frames, base: InspectorConfig, spec: dict, part: str):
    """Calibrated InspectorConfig from one camera view's frames (None if impossible)."""
    roi = tuple(base.roi)
    key_of = (lambda r: "good" if r["ground_truth"] == "good" else f"defect:{r.get('defect_kind') or '?'}")

    cfg = InspectorConfig(roi=None, val_min=base.val_min, min_area_px=base.min_area_px,
                          hue_tolerance=base.hue_tolerance, good_ratio_min=base.good_ratio_min)

    if spec.get("segment", "saturation") == "saturation":
        good_hues, sats = [], []
        for row, rgb in frames:
            px = product_pixels(rgb, roi, base.val_min)
            if px is None:
                continue
            sats.append(np.percentile(px[:, 1], 5))
            if row["ground_truth"] == "good":
                good_hues.append(px[:, 0])
        if not good_hues:
            print("No good-product frames with a detectable blob; cannot calibrate.")
            return None
        cfg.sat_min = int(max(PERMISSIVE_SAT, 0.6 * min(sats)))
        cfg.reference_hue = round(circular_mean_hue(np.concatenate(good_hues)), 2)
        print(f"product saturation p5 per frame: min={min(sats):.0f} median={np.median(sats):.0f}")
    else:  # bright segmentation + Lab a*b* shade (white products)
        cfg.segment, cfg.color_metric = "bright", "ab"
        probe = VisionInspector(InspectorConfig(**{**cfg.__dict__, "roi": roi}))
        ab_px, good = [], []
        for row, rgb in frames:
            if row["ground_truth"] != "good":
                continue
            r = probe.inspect(rgb)
            if r.contour is None:
                continue
            x0, y0, x1, y1 = roi
            lab = cv2.cvtColor(rgb[y0:y1, x0:x1], cv2.COLOR_RGB2LAB)
            filled = np.zeros(lab.shape[:2], np.uint8)
            cv2.drawContours(filled, [np.array(r.contour, np.int32)], -1, 1, cv2.FILLED)
            ab_px.append(lab[:, :, 1:3][filled > 0].astype(np.float32))
            good.append(r)
        if not good:
            print("No good-product frames with a detectable silhouette; cannot calibrate.")
            return None
        allab = np.concatenate(ab_px)
        ref = np.median(allab, axis=0)
        dist = np.linalg.norm(allab - ref, axis=1)
        cfg.reference_ab = (round(float(ref[0]), 2), round(float(ref[1]), 2))
        cfg.ab_tolerance = round(float(max(6.0, 1.5 * np.percentile(dist, 90))), 2)
        print(f"reference_ab={cfg.reference_ab} ab_tolerance={cfg.ab_tolerance}")

    probe_cfg = InspectorConfig(**{**cfg.__dict__, "roi": roi, "good_ratio_min": 0.0})
    if spec.get("interior_check"):
        probe_cfg.interior_bright_min = 0.0
    results_by = {}
    for row, rgb in frames:
        results_by.setdefault(key_of(row), []).append((row, VisionInspector(probe_cfg).inspect(rgb)))
    goods = [r for _, r in results_by.get("good", []) if r.contour is not None]
    if not goods:
        print("No good results; cannot calibrate.")
        return None

    if part != "box":
        cfg.good_ratio_min = round(float(0.8 * min(r.score for r in goods)), 3)
    if spec.get("interior_check"):
        cfg.interior_bright_min = round(float(0.5 * min(r.interior_bright for r in goods)), 3)
    if spec.get("golden_contour"):
        areas = [cv2.contourArea(np.array(r.contour, np.int32)) for r in goods]
        golden = goods[int(np.argsort(areas)[len(areas) // 2])]
        cfg.golden_contour = golden.contour
        cfg.golden_area_px = float(cv2.contourArea(np.array(golden.contour, np.int32)))
        gc = np.array(golden.contour, np.int32).reshape(-1, 1, 2)
        dists = [cv2.matchShapes(np.array(r.contour, np.int32).reshape(-1, 1, 2), gc, cv2.CONTOURS_MATCH_I1, 0.0)
                 for r in goods]
        ratios = [a / cfg.golden_area_px for a in areas]
        cfg.shape_dist_max = round(float(max(0.02, 2.0 * max(dists))), 4)
        cfg.area_ratio_tol = round(float(max(0.05, 2.0 * max(abs(x - 1.0) for x in ratios))), 4)
        if spec.get("silhouette_check"):
            sil = [silhouette_diff(r.contour, golden.contour) for r in goods]
            cfg.silhouette_diff_max = round(float(max(0.02, 2.0 * max(sil))), 4)
        # information: how the defect frames compare (not used for thresholds)
        for key, items in sorted(results_by.items()):
            ds = [cv2.matchShapes(np.array(r.contour, np.int32).reshape(-1, 1, 2), gc, cv2.CONTOURS_MATCH_I1, 0.0)
                  for _, r in items if r.contour is not None]
            ar = [cv2.contourArea(np.array(r.contour, np.int32)) / cfg.golden_area_px for _, r in items if r.contour]
            sc = [r.score for _, r in items]
            sd = [silhouette_diff(r.contour, golden.contour) for _, r in items if r.contour]
            print(f"  {key:16s} n={len(items):2d} score min/max={min(sc):.2f}/{max(sc):.2f} "
                  f"contour dist max={max(ds) if ds else float('nan'):.3f} area ratio {min(ar):.2f}..{max(ar):.2f} "
                  f"silhouette diff {min(sd) if sd else float('nan'):.3f}..{max(sd) if sd else float('nan'):.3f}")
    elif part != "box":
        print_stats("", {k: [(r.score, r.interior_bright) for _, r in v] for k, v in results_by.items()},
                    ["score", "interior_bright"])

    print(f"good_ratio_min={cfg.good_ratio_min} interior_bright_min={cfg.interior_bright_min} "
          f"shape_dist_max={cfg.shape_dist_max} area_ratio_tol={cfg.area_ratio_tol} "
          f"silhouette_diff_max={cfg.silhouette_diff_max}")
    return cfg


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    run_dir = Path(sys.argv[1])
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    part = run.get("part", "box")
    base = InspectorConfig(**{k: v for k, v in run["inspector"].items() if k in InspectorConfig.__dataclass_fields__})
    out = ROOT / "config" / ("inspector.json" if part == "box" else f"inspector_{part}.json")
    spec = {}
    if part != "box":
        spec = json.loads((ROOT / "assets/parts/catalog.json").read_text(encoding="utf-8"))[part].get("inspection", {})

    with open(run_dir / "inspections.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    results = run_dir / "results.csv"
    if results.exists():  # ground-truth defect kind lives in results.csv
        with open(results, encoding="utf-8") as f:
            kinds = {r["product_id"]: r.get("defect_kind", "") for r in csv.DictReader(f)}
        for r in rows:
            r["defect_kind"] = kinds.get(r["product_id"], "")
    print(f"calibration run: {run_dir.name} part={part} rows={len(rows)} inspection={spec or 'box default'}")
    multi = run.get("views")
    if multi:  # inspection cell: one calibration per view, from that view's frames only
        cfgs = []
        for k, name in enumerate(multi):
            base_k = InspectorConfig(**{key: v for key, v in run["view_inspectors"][k].items()
                                        if key in InspectorConfig.__dataclass_fields__})
            view_rows = [r for r in rows if str(r.get("view")) == str(k) and r["frame_file"]]
            print(f"--- view {k} ({name}): {len(view_rows)} frames")
            cfg = calibrate(load_frames(run_dir, view_rows), base_k, spec, part)
            if cfg is None:
                return 1
            cfgs.append(cfg)
        out.parent.mkdir(parents=True, exist_ok=True)
        save_view_configs(str(out), cfgs, multi)
        print(f"{len(cfgs)} view configs -> {out}")
        return 0
    rows = product_rows(rows)
    cfg = calibrate(load_frames(run_dir, rows), base, spec, part)
    if cfg is None:
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg.save(str(out))
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
