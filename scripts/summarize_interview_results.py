"""Aggregate interview timing and instancing artifacts without inventing missing results.

Usage: summarize_interview_results.py. Outputs results/interview/report.md and report.json.
"""

import json
import csv
from pathlib import Path
import statistics
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/interview"


def percentile(xs, q):
    xs = sorted(xs)
    k = (len(xs)-1)*q
    a = int(k)
    return xs[a] + (xs[min(a+1, len(xs)-1)]-xs[a])*(k-a)


def main():
    data = {"composition": [], "instancing": [], "timing": [], "lifecycle": [], "frame_content": [], "lod": [], "lifecycle_pending": []}
    lines = ["# Interview verification results", "", "Generated from raw artifacts. Missing experiments remain unmeasured.", ""]
    comparison_path = OUT / "baseline/comparison.json"
    if comparison_path.exists():
        pairs = json.loads(comparison_path.read_text(encoding="utf-8-sig"))
        data["baseline_comparisons"] = pairs
        lines += ["## Before/after outcome regression", "", "| part | repeat | identical outcomes |", "|---|---|---|"]
        for pair in pairs:
            lines.append(f"| {pair['part']} | {pair['repeat']} | {pair['identical']} |")
        if not all(p["identical"] for p in pairs):
            lines += ["", "**REGRESSION CHECK FAILED. Differences are preserved; this report does not claim full acceptance.**", ""]
    duplicate_path = OUT / "capture_duplicate_audit.json"
    if duplicate_path.exists():
        audit = json.loads(duplicate_path.read_text(encoding="utf-8"))
        data["capture_duplicates"] = audit
        lines += ["## Captured content investigation", "", f"- Identical consecutive capture pairs: {audit['identical_pairs']}; conflicting offline expected labels: {audit['conflicting_expected_labels']}.",
                  "- Frame number equality does not establish image/state equality. See capture_duplicate_audit.json for raw paths and hashes.",
                  "- The historical content mismatch has an unresolved native root cause; successful controlled reruns do not establish its resolution.",
                  "- Offline expected labels are used for diagnosis only; no ground truth enters runtime inspection.", ""]
    for path in sorted(OUT.glob("composition/*/report.json")):
        report = json.loads(path.read_text(encoding="utf-8-sig"))
        data["composition"].append(dict(path=str(path.relative_to(ROOT)), **report))
        lines.append(f"- Composition: {len(report['checks'])} asserted checks passed ({path.parent.name}).")
    for manifest in sorted(OUT.glob("instancing/*/manifest.json")):
        content = json.loads(manifest.read_text(encoding="utf-8"))
        lines += ["", "## Repeated CAD assets", "", "| mode | count | CPU open ms (median) | CPU RSS MiB (median) | Kit update p50 ms | Kit update p95 ms | render runs |", "|---|---|---|---|---|---|---|"]
        for entry in content["entries"]:
            rows = [r for r in content["cpu"] if r["mode"] == entry["mode"] and r["count"] == entry["count"]]
            renders = [json.loads(p.read_text(encoding="utf-8")) for p in manifest.parent.glob(f"render/**/{entry['mode']}_{entry['count']}_*/render.json")]
            samples = [x for r in renders for x in r["update_ms"]]
            item = dict(**entry, cpu_open_ms=statistics.median(r["open_s"]*1000 for r in rows),
                        rss_mib=statistics.median(r["after"]["rss_bytes"]/1024**2 for r in rows),
                        render_runs=len(renders), update_p50=percentile(samples,0.5) if samples else None,
                        update_p95=percentile(samples,0.95) if samples else None)
            item["kit_rss_mib"] = statistics.median(r["memory"]["rss_bytes"]/1024**2 for r in renders) if renders else None
            item["kit_stage_open_ms"] = statistics.median(r["stage_open_s"]*1000 for r in renders) if renders else None
            item["first_viewport_frame_s"] = statistics.median(r["first_viewport_frame_s"] for r in renders) if renders else None
            devices = [r["gpu"]["device_used_mib"][0] for r in renders if r["gpu"]["device_used_mib"]]
            item["device_gpu_mib"] = statistics.median(devices) if devices else None
            data["instancing"].append(item)
            lines.append(f"| {entry['mode']} | {entry['count']} | {item['cpu_open_ms']:.2f} | {item['rss_mib']:.1f} | {item['update_p50']} | {item['update_p95']} | {len(renders)} |")
        lines += ["", "## Kit loading and memory (medians)", "", "| mode | count | stage open ms | first viewport frame s | process RSS MiB | whole-device GPU MiB |", "|---|---|---|---|---|---|"]
        for item in data["instancing"]:
            lines.append(f"| {item['mode']} | {item['count']} | {item['kit_stage_open_ms']} | {item['first_viewport_frame_s']} | {item['kit_rss_mib']} | {item['device_gpu_mib']} |")
    timing_paths = sorted(OUT.glob("timing/**/timing.json")) + sorted(OUT.glob("baseline/**/timing.json"))
    for path in timing_paths:
        item = json.loads(path.read_text(encoding="utf-8"))
        summary_file = path.parent / "summary.json"
        summary = json.loads(summary_file.read_text(encoding="utf-8")) if summary_file.exists() else {}
        starts, product_latencies = {}, []
        trace_file = path.parent / "trace.csv"
        if trace_file.exists():
            with open(trace_file, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    pid = row["product_id"]
                    if row["event"] == "CAPTURE_REQUESTED":
                        starts.setdefault(pid, float(row["wall_s"]))
                    elif row["event"] == "VERDICT_APPLIED" and pid in starts:
                        product_latencies.append((float(row["wall_s"])-starts[pid])*1000)
        item["product_verdict_ms"] = dict(n=len(product_latencies),
            p95=percentile(product_latencies,0.95) if product_latencies else None,
            definition="first capture request of product to applied verdict; includes unknown/fail-safe; excludes late verdicts")
        data["timing"].append(dict(path=str(path.relative_to(ROOT)), result=summary, **item))
    groups = defaultdict(list)
    for item in data["timing"]:
        if "timing" in Path(item["path"]).parts:
            groups[Path(item["path"]).parts[-4].rsplit("_",1)[0]].append(item)
    data["timing_conditions"] = []
    lines += ["", "## Timing conditions (repetitions reuse the configured seed)", "", "| condition | runs | RTF median | capture p95 median ms | route correct / total | timeouts | fail-safe rejects |", "|---|---|---|---|---|---|---|"]
    for condition, items in sorted(groups.items()):
        captures = [v["latency_ms"]["capture"]["p95"] for v in items if v["latency_ms"]["capture"]["p95"] is not None]
        row = dict(condition=condition, runs=len(items), rtf_median=statistics.median(v["real_time_factor"] for v in items),
            capture_p95_median=statistics.median(captures) if captures else None,
            route_correct=sum(v["result"].get("sort_correct",0) for v in items),
            products=sum(v["result"].get("products",0) for v in items),
            timeouts=sum(v["result"].get("capture_timeouts",0) for v in items),
            fail_safe_rejects=sum(v["result"].get("fail_safe_rejects",0) for v in items))
        data["timing_conditions"].append(row)
        lines.append(f"| {condition} | {row['runs']} | {row['rtf_median']:.3f} | {row['capture_p95_median']} | {row['route_correct']}/{row['products']} | {row['timeouts']} | {row['fail_safe_rejects']} |")
    lines += ["", "## Timing runs", "", "| run | status | wall s | RTF | capture p95 ms | max pending | correct/sorted | timeouts | late |", "|---|---|---|---|---|---|---|---|---|"]
    for item in data["timing"]:
        result = item["result"]
        lines.append(f"| {item['path']} | {item['status']} | {item['wall_s']} | {item['real_time_factor']} | {item['latency_ms']['capture']['p95']} | {item['max_pending']} | {result.get('sort_correct')}/{result.get('sorted')} | {result.get('capture_timeouts')} | {result.get('late_results')} |")
    for path in sorted(OUT.glob("lifecycle/*/report.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        data["lifecycle"].append(dict(path=str(path.relative_to(ROOT)), **item))
    lines += ["", "## Lifecycle", ""]
    for item in data["lifecycle"]:
        lines.append(f"- {item['mode']}: {len(item['rows'])} checks, stale callbacks applied={item['stale_callbacks_applied']}, expected behavior verified={item['pass_expected_behavior']}")
    for path in sorted(OUT.glob("lifecycle_pending/*/report.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        data["lifecycle_pending"].append(dict(path=str(path.relative_to(ROOT)), **item))
        lines.append(f"- Native pending: {len(item['rows'])} checks, callback pending before transition={item['native_callback_pending_before_transition']}, passed={item['passed']}")
    lines += ["", "## LOD (50 instances)", "", "| LOD | render runs | update p50 ms | update p95 ms | Kit RSS MiB median |", "|---|---|---|---|---|"]
    for manifest in sorted(OUT.glob("lod/*/manifest.json")):
        for entry in json.loads(manifest.read_text(encoding="utf-8"))["entries"]:
            renders = [json.loads(p.read_text(encoding="utf-8")) for p in manifest.parent.glob(f"render/**/{entry['mode']}_50_*/render.json")]
            if not renders:
                continue
            samples = [v for r in renders for v in r["update_ms"]]
            item = dict(lod=entry["lod"], runs=len(renders), update_p50=percentile(samples,0.5),
                update_p95=percentile(samples,0.95), rss_mib=statistics.median(r["memory"]["rss_bytes"]/1024**2 for r in renders))
            data["lod"].append(item)
            lines.append(f"| {item['lod']} | {item['runs']} | {item['update_p50']} | {item['update_p95']} | {item['rss_mib']} |")
    lines += ["", "## Frame content", ""]
    for path in sorted(OUT.glob("frame_content/*/report.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        data["frame_content"].append(dict(path=str(path.relative_to(ROOT)), **item))
        lines.append(f"- {path.parent.name}: samples={len(item['samples'])}, mismatches={item['mismatches']}, undecodable={item['undecodable']}, errors={item['errors']}")
    lines += ["", "## Measurement limits", "", "- Kit update intervals include CPU and rendering; they are not GPU-only frame durations.",
              "- GPU memory snapshots are device-wide, not per-process VRAM.", "- Fresh process does not imply cold OS, shader or driver caches.",
              "- Instancing can trade editing flexibility for sharing; no speedup is assumed.", "- Timing p95 excludes timed-out requests; event counts must be read alongside latency."]
    lines.append("- Raw verdict latency starts at the final callback's capture request; product_verdict_ms in report.json uses the product's first capture request.")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (OUT / "report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(f"Summary: {OUT / 'report.md'}")


if __name__ == "__main__":
    main()
