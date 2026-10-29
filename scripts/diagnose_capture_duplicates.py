"""Audit identical capture pixels against recorded labels, without changing runtime decisions.

Usage: diagnose_capture_duplicates.py. Reads completed after baselines, writes
results/interview/capture_duplicate_audit.json. Ground truth is used only offline.
"""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/interview"


def main():
    rows = []
    for trace_path in sorted(BASE.glob("baseline/after_*/box_*/runs/*/trace.csv")):
        run = trace_path.parent
        if not (run / "summary.json").exists():
            continue
        with (run / "inspections.csv").open(encoding="utf-8-sig", newline="") as file:
            inspections = {r["product_id"]: r for r in csv.DictReader(file)}
        previous = None
        with trace_path.open(encoding="utf-8-sig", newline="") as file:
            for event in csv.DictReader(file):
                if event["event"] != "CAPTURE_RECEIVED":
                    continue
                if previous and event["digest"] == previous["digest"]:
                    a, b = (inspections[e["product_id"]] for e in (previous, event))
                    a_path, b_path = (run / r["frame_file"] for r in (a, b))
                    a_bytes, b_bytes = a_path.read_bytes(), b_path.read_bytes()
                    rows.append(dict(run=str(run.relative_to(ROOT)),
                        previous_product=a["product_id"], product=b["product_id"],
                        previous_ground_truth=a["ground_truth"], ground_truth=b["ground_truth"],
                        prediction=b["predicted_label"],
                        png_bytes_identical=a_bytes == b_bytes,
                        png_sha256=hashlib.sha256(b_bytes).hexdigest(),
                        previous_frame=str(a_path.relative_to(ROOT)), frame=str(b_path.relative_to(ROOT)),
                        previous_target=previous["target_frame"], target=event["target_frame"],
                        captured=event["captured_frame"], rgb_digest=event["digest"],
                        conflicting_expected_labels=a["ground_truth"] != b["ground_truth"]))
                previous = event
    report = dict(rows=rows, identical_pairs=len(rows),
        conflicting_expected_labels=sum(r["conflicting_expected_labels"] for r in rows),
        note="Offline evidence only. Identical pixels can be legitimate; label conflict does not identify the native renderer root cause. No ground-truth information enters the inspector.")
    path = BASE / "capture_duplicate_audit.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Duplicate capture audit: {len(rows)} pairs, {report['conflicting_expected_labels']} label conflicts. {path}")


if __name__ == "__main__":
    main()
