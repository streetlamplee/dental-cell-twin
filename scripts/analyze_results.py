"""Analyse an experiment (system Python: pandas + matplotlib). Uses only recorded files:
run.json, summary.json, results.csv, inspections.csv of every run in
results/experiments/<name>/runs/. Nothing is estimated: a metric without data is N/A.

Outputs (results/experiments/<name>/):
  table.csv / table.md      one row per condition
  fig_vision.png            sort success rate per condition, small multiples by product
  fig_line.png              dental line: utilisation, max queue, throughput vs spawn interval

Usage: python scripts/analyze_results.py <name>
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/extensions/visiontwin.factory/visiontwin/factory"))

from core.metrics import confusion, percentile, precision_recall_f1  # noqa: E402

# Chart tokens (dataviz reference palette, light mode): categorical slots in fixed order.
SURFACE, TEXT, TEXT2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
PRODUCT_COLOR = {"box": "#2a78d6", "kfl08": "#eb6834", "crown": "#1baf7a"}  # slots 1, 2, 3
PRODUCT_NAME = {"box": "Box (colour)", "kfl08": "KFL08 bearing", "crown": "Dental crown"}
KIND_TO_REASON = {"color": "color", "missing": "shape", "shape": "shape"}


def fmt(x, digits=3):
    return "N/A" if x is None or (isinstance(x, float) and pd.isna(x)) else (
        f"{x:.{digits}f}" if isinstance(x, float) else str(x))


def analyse_run(run_dir: Path) -> dict:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    res = pd.read_csv(run_dir / "results.csv", dtype={"predicted_label": str, "defect_kind": str}).fillna("")
    insp = pd.read_csv(run_dir / "inspections.csv")
    gts = list(res["ground_truth"])
    preds = [p if p in ("good", "defect") else "unknown" for p in res["predicted_label"]]
    c = confusion(gts, preds)
    p, r, f1 = precision_recall_f1(c)
    row = {
        "condition": run.get("condition", run_dir.name), "group": "", "part": run.get("part", "box"),
        "lighting": run.get("lighting_condition"), "speed_mps": run.get("conveyor_speed"),
        "products": len(res), "good": gts.count("good"), "defect": gts.count("defect"),
        "TP": c["tp"], "FP": c["fp"], "FN": c["fn"], "TN": c["tn"], "unknown": c["unknown"],
        "precision": p, "recall": r, "f1": f1,
        "sort_success": summary["sort_correct"] / summary["sorted"] if summary.get("sorted") else None,
        "fail_safe": summary.get("fail_safe_rejects"),
        "capture_ms_mean": float(insp["capture_latency_ms"].mean()) if len(insp) else None,
        "capture_ms_p95": percentile(insp["capture_latency_ms"], 95) if len(insp) else None,
        "inspect_ms_mean": float(insp["inspection_latency_ms"].mean()) if len(insp) else None,
        "inspect_ms_p95": percentile(insp["inspection_latency_ms"], 95) if len(insp) else None,
        "throughput_per_h": summary.get("throughput_per_hour"),
        "sim_time_s": summary.get("simulation_time_s"),
    }
    for kind in ("color", "missing", "shape"):
        sel = res[(res["ground_truth"] == "defect") & (res["defect_kind"] == kind)]
        row[f"recall_{kind}"] = (sel["predicted_label"] == "defect").mean() if len(sel) else None
    line = summary.get("line")
    row.update({
        "spawn_interval_s": line["spawn_interval_s"] if line else None,
        "cycle_s": line["cycle_s_compressed"] if line else None,
        "utilization": line["station_utilization"] if line else None,
        "queue_max": line["queue_max"] if line else None,
        "queue_mean": line["queue_mean"] if line else None,
    })
    return row


def style(ax, title):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, color=TEXT, fontsize=11, loc="left")
    ax.tick_params(colors=TEXT2, labelsize=9)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def fig_vision(df: pd.DataFrame, out: Path) -> None:
    vis = df[df["group"] == "vision"]
    parts = [p for p in ("box", "kfl08", "crown") if p in set(vis["part"])]
    if not parts:
        return
    fig, axes = plt.subplots(1, len(parts), figsize=(4.2 * len(parts), 3.6), sharey=True, facecolor=SURFACE)
    axes = [axes] if len(parts) == 1 else list(axes)
    for ax, part in zip(axes, parts):
        sub = vis[vis["part"] == part].copy()
        sub["label"] = sub["condition"].str.replace(f"{part}_", "", regex=False)
        bars = ax.bar(sub["label"], sub["sort_success"], width=0.55, color=PRODUCT_COLOR[part],
                      edgecolor=SURFACE, linewidth=2)
        for b, v, rec in zip(bars, sub["sort_success"], sub["recall"]):
            ax.text(b.get_x() + b.get_width() / 2, (v or 0) + 0.02,
                    f"{v:.2f}\nrecall {fmt(rec, 2)}", ha="center", va="bottom", fontsize=8, color=TEXT)
        style(ax, PRODUCT_NAME[part])
        ax.set_ylim(0, 1.25)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    axes[0].set_ylabel("Sort success rate", color=TEXT2)
    fig.suptitle("Sort success by condition (thresholds calibrated under default lighting)",
                 color=TEXT, fontsize=12, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def fig_line(df: pd.DataFrame, out: Path) -> None:
    line = df[df["group"] == "line"].sort_values("spawn_interval_s")
    if line.empty:
        return
    metrics = [("utilization", "Mill utilisation", "{:.0%}"), ("queue_max", "Max queue (products)", "{:.0f}"),
               ("throughput_per_h", "Throughput (/h, compressed time)", "{:.0f}")]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), facecolor=SURFACE)
    color = PRODUCT_COLOR["crown"]
    for ax, (col, title, f) in zip(axes, metrics):
        x, y = line["spawn_interval_s"], line[col]
        ax.plot(x, y, color=color, linewidth=2, marker="o", markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2)
        for xi, yi in zip(x, y):
            ax.annotate(f.format(yi), (xi, yi), textcoords="offset points", xytext=(0, 9),
                        ha="center", fontsize=8, color=TEXT)
        style(ax, title)
        ax.set_xlabel("Spawn interval (s), mill cycle 3 s", color=TEXT2, fontsize=9)
        ax.set_xticks(list(x))
        ymax = max(y) if len(y) else 1
        ax.set_ylim(0, ymax * 1.25 if ymax else 1)
    fig.suptitle("Dental milling line: arrivals vs mill capacity", color=TEXT, fontsize=12, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    name = sys.argv[1]
    exp_dir = ROOT / "results" / "experiments" / name
    conf = json.loads((ROOT / "experiments" / f"{name}.json").read_text(encoding="utf-8"))
    groups = {r["condition"]: r.get("group", "") for r in conf["runs"]}
    order = [r["condition"] for r in conf["runs"]]
    rows = []
    for run_dir in sorted((exp_dir / "runs").glob("*")):
        if (run_dir / "summary.json").exists() and (run_dir / "results.csv").exists():
            row = analyse_run(run_dir)
            row["group"] = groups.get(row["condition"], "")
            rows.append(row)
    if not rows:
        print(f"No finished runs in {exp_dir / 'runs'}")
        return 1
    df = pd.DataFrame(rows)
    df["order"] = df["condition"].map({c: i for i, c in enumerate(order)})
    df = df.sort_values("order").drop(columns="order")
    df.to_csv(exp_dir / "table.csv", index=False)

    cols = ["condition", "products", "good", "defect", "TP", "FP", "FN", "TN", "unknown", "precision", "recall",
            "f1", "sort_success", "recall_color", "recall_missing", "recall_shape", "capture_ms_mean",
            "capture_ms_p95", "inspect_ms_mean", "inspect_ms_p95", "throughput_per_h", "utilization",
            "queue_max", "queue_mean"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(fmt(r[c], 3 if isinstance(r[c], float) else 0) for c in cols) + " |")
    (exp_dir / "table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    fig_vision(df, exp_dir / "fig_vision.png")
    fig_line(df, exp_dir / "fig_line.png")
    missing = [c for c in order if c not in set(df["condition"])]
    print(f"{len(df)} runs analysed -> {exp_dir / 'table.md'}, fig_vision.png, fig_line.png")
    if missing:
        print(f"not finished: {', '.join(missing)}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
