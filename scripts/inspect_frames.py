"""Offline batch inspection of a recorded run (system Python, no Kit).

Re-runs VisionInspector on every saved frame of a run, writes
<run>/offline/predictions.csv, copies misclassified frames (with ROI/bbox overlay)
to <run>/offline/errors/, and prints metrics. Ground truth is read from
inspections.csv only to evaluate; the inspector itself only receives pixels.

Usage: python scripts/inspect_frames.py <run_dir> [--config config/inspector.json]
"""

import argparse
import csv
import json
import os
import shutil
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/extensions/visiontwin.factory/visiontwin/factory"))

from core.metrics import accuracy, confusion, fmt, percentile, precision_recall_f1  # noqa: E402
from core.vision_inspector import InspectorConfig, VisionInspector  # noqa: E402


def load_config(run_dir: Path, override: str) -> InspectorConfig:
    with open(run_dir / "run.json", encoding="utf-8") as f:
        run_cfg = json.load(f)["inspector"]
    cfg = InspectorConfig(**run_cfg)
    cfg.roi = tuple(cfg.roi) if cfg.roi else None
    if override:
        # Calibrated values replace the run's, but the run's ROI (camera geometry) is kept.
        tuned = InspectorConfig.load(override)
        roi = cfg.roi
        cfg = tuned
        cfg.roi = tuned.roi or roi
    return cfg


def overlay(bgr, roi, bbox, text):
    out = bgr.copy()
    x0, y0, x1, y1 = roi
    cv2.rectangle(out, (x0, y0), (x1 - 1, y1 - 1), (255, 255, 0), 1)
    if bbox:
        x, y, w, h = bbox
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 0, 255), 2)
    cv2.putText(out, text, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--config", default="")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    cfg = load_config(run_dir, args.config)
    inspector = VisionInspector(cfg)

    out_dir = run_dir / "offline"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "errors").mkdir(parents=True)

    with open(run_dir / "inspections.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("No inspections recorded in this run.")
        return 1
    kinds = {}
    if (run_dir / "results.csv").exists():  # ground-truth defect kind (evaluation only)
        with open(run_dir / "results.csv", encoding="utf-8") as f:
            kinds = {r["product_id"]: r.get("defect_kind", "") for r in csv.DictReader(f)}

    gts, preds, lat, mismatched_online = [], [], [], 0
    by_kind = {}  # defect kind -> [detected, total, reason matches]
    with open(out_dir / "predictions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["product_id", "ground_truth", "defect_kind", "online_label", "offline_label",
                    "defect_reason", "score", "interior_bright", "mean_hue", "area_px", "latency_ms",
                    "reason", "frame_file"])
        for row in rows:
            bgr = cv2.imread(str(run_dir / row["frame_file"]))
            res = inspector.inspect(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            kind = kinds.get(row["product_id"], "")
            gts.append(row["ground_truth"])
            preds.append(res.label)
            lat.append(res.latency_ms)
            mismatched_online += res.label != row["predicted_label"]
            if row["ground_truth"] == "defect":
                k = by_kind.setdefault(kind or "?", [0, 0, 0])
                k[0] += res.label == "defect"
                k[1] += 1
                k[2] += {"color": "color", "missing": "shape", "shape": "shape"}.get(kind) in res.defect_reason.split("+")
            w.writerow([row["product_id"], row["ground_truth"], kind, row["predicted_label"], res.label,
                        res.defect_reason, f"{res.score:.4f}", f"{res.interior_bright:.4f}",
                        f"{res.mean_hue:.2f}", res.area_px, f"{res.latency_ms:.3f}", res.reason, row["frame_file"]])
            if res.label != row["ground_truth"]:
                text = f"id={row['product_id']} gt={row['ground_truth']} pred={res.label} s={res.score:.2f}"
                cv2.imwrite(str(out_dir / "errors" / Path(row["frame_file"]).name),
                            overlay(bgr, cfg.roi or (0, 0, bgr.shape[1], bgr.shape[0]), res.bbox, text))

    c = confusion(gts, preds)
    p, r, f1 = precision_recall_f1(c)
    print(f"run: {run_dir.name}  frames: {len(rows)}  (good={gts.count('good')}, defect={gts.count('defect')})")
    print(f"config: {cfg}")
    print(f"confusion (defect=positive): TP={c['tp']} FP={c['fp']} FN={c['fn']} TN={c['tn']} unknown={c['unknown']}")
    print(f"accuracy={fmt(accuracy(gts, preds))} precision={fmt(p)} recall={fmt(r)} f1={fmt(f1)}")
    for kind, (hit, total, reason_ok) in sorted(by_kind.items()):
        print(f"  defect kind {kind:8s}: recall {hit}/{total} = {fmt(hit / total)}, "
              f"reason matches kind {reason_ok}/{total}")
    print(f"offline inspection latency ms: mean={fmt(sum(lat) / len(lat), 2)} p95={fmt(percentile(lat, 95), 2)}")
    print(f"offline vs online label mismatches: {mismatched_online}")
    print(f"misclassified frames: {len(os.listdir(out_dir / 'errors'))} -> {out_dir / 'errors'}")
    print(f"predictions: {out_dir / 'predictions.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
