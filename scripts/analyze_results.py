"""Analyse an experiment (system Python: pandas + matplotlib). Uses only recorded files:
run.json, summary.json, results.csv, inspections.csv of every run in
results/experiments/<name>/runs/. Nothing is estimated: a metric without data is N/A.

Outputs (results/experiments/<name>/):
  table.csv / table.md      one row per condition
  fig_vision.png            sort success rate per condition, small multiples by product
  fig_views.png             inspection cell: defect recall per kind, top view only vs all views
                            (from the same runs: view 0 rows vs the combined rows)
  fig_line.png              station line: utilisation, max queue, throughput vs spawn interval

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
KIND_TO_REASON = {"color": "color", "missing": "shape", "shape": "shape", "chip": "shape"}
DEFECT_KINDS = ("color", "missing", "shape", "chip")
VIEW_SERIES = (("top", "Top view only", "#2a78d6"), ("all", "Top + 4 side views", "#eb6834"))  # slots 1, 2


def fmt(x, digits=3):
    return "N/A" if x is None or (isinstance(x, float) and pd.isna(x)) else (
        f"{x:.{digits}f}" if isinstance(x, float) else str(x))


def analyse_run(run_dir: Path) -> dict:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    res = pd.read_csv(run_dir / "results.csv", dtype={"predicted_label": str, "defect_kind": str}).fillna("")
    insp = pd.read_csv(run_dir / "inspections.csv", dtype={"view": str})
    multi = "view" in insp and (insp["view"] == "all").any()
    captures = insp[insp["view"] != "all"] if multi else insp  # one row per captured frame
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
        "capture_ms_mean": float(captures["capture_latency_ms"].mean()) if len(captures) else None,
        "capture_ms_p95": percentile(captures["capture_latency_ms"], 95) if len(captures) else None,
        "inspect_ms_mean": float(captures["inspection_latency_ms"].mean()) if len(captures) else None,
        "inspect_ms_p95": percentile(captures["inspection_latency_ms"], 95) if len(captures) else None,
        "throughput_per_h": summary.get("throughput_per_hour"),
        "sim_time_s": summary.get("simulation_time_s"),
    }
    for kind in DEFECT_KINDS:
        sel = res[(res["ground_truth"] == "defect") & (res["defect_kind"] == kind)]
        row[f"recall_{kind}"] = (sel["predicted_label"] == "defect").mean() if len(sel) else None
    # Inspection cell: the same products judged from the top view alone (view 0 verdicts).
    row["recall_top_only"] = row["precision_top_only"] = None
    row.update({f"recall_top_{kind}": None for kind in DEFECT_KINDS})
    if multi:
        top = dict(zip(insp[insp["view"] == "0"]["product_id"], insp[insp["view"] == "0"]["predicted_label"]))
        res_top = res.assign(top=[top.get(pid, "unknown") for pid in res["product_id"]])
        ct = confusion(gts, [p if p in ("good", "defect") else "unknown" for p in res_top["top"]])
        row["precision_top_only"], row["recall_top_only"], _ = precision_recall_f1(ct)
        for kind in DEFECT_KINDS:
            sel = res_top[(res_top["ground_truth"] == "defect") & (res_top["defect_kind"] == kind)]
            row[f"recall_top_{kind}"] = (sel["top"] == "defect").mean() if len(sel) else None
    line = summary.get("line")
    row.update({
        "spawn_interval_s": line["spawn_interval_s"] if line else None,
        "cycle_s": (line.get("cycle_s") or line.get("cycle_s_compressed")) if line else None,
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


def fig_views(df: pd.DataFrame, out: Path) -> None:
    """Defect recall per kind for the inspection cell: top view only vs all views (same runs)."""
    vis = df[(df["group"] == "vision") & df["recall_top_only"].notna()]
    if vis.empty:
        return
    conds = list(vis["condition"])
    fig, axes = plt.subplots(1, len(conds), figsize=(4.4 * len(conds), 3.8), sharey=True, facecolor=SURFACE)
    axes = [axes] if len(conds) == 1 else list(axes)
    for ax, (_, r) in zip(axes, vis.iterrows()):
        kinds = [k for k in DEFECT_KINDS if r.get(f"recall_{k}") is not None and not pd.isna(r.get(f"recall_{k}"))]
        xs = range(len(kinds))
        for i, (key, label, color) in enumerate(VIEW_SERIES):
            vals = [r[f"recall_top_{k}"] if key == "top" else r[f"recall_{k}"] for k in kinds]
            pos = [x + (i - 0.5) * 0.36 for x in xs]
            bars = ax.bar(pos, vals, width=0.34, color=color, edgecolor=SURFACE, linewidth=2, label=label)
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}", ha="center", va="bottom",
                        fontsize=8, color=TEXT)
        style(ax, r["condition"])
        ax.set_xticks(list(xs))
        ax.set_xticklabels(kinds)
        ax.set_ylim(0, 1.2)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    axes[0].set_ylabel("Defect recall", color=TEXT2)
    axes[0].legend(frameon=False, fontsize=8, labelcolor=TEXT, loc="lower left")
    fig.suptitle("Inspection cell: recall per defect kind, top view only vs top + 4 side views (same runs)",
                 color=TEXT, fontsize=12, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def fig_line(df: pd.DataFrame, out: Path) -> None:
    line = df[df["group"] == "line"].sort_values("spawn_interval_s")
    if line.empty:
        return
    metrics = [("utilization", "Station utilisation", "{:.0%}"), ("queue_max", "Max queue (products)", "{:.0f}"),
               ("throughput_per_h", "Throughput (/h)", "{:.0f}")]
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
        ax.set_xlabel(f"Spawn interval (s), station cycle {line['cycle_s'].iloc[0]:.1f} s", color=TEXT2, fontsize=9)
        ax.set_xticks(list(x))
        ymax = max(y) if len(y) else 1
        ax.set_ylim(0, ymax * 1.25 if ymax else 1)
    fig.suptitle("Dental crown line: arrivals vs station capacity", color=TEXT, fontsize=12, x=0.01, ha="left")
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
            "f1", "sort_success", "recall_color", "recall_missing", "recall_shape", "recall_chip",
            "recall_top_only", "recall_top_chip", "capture_ms_mean",
            "capture_ms_p95", "inspect_ms_mean", "inspect_ms_p95", "throughput_per_h", "utilization",
            "queue_max", "queue_mean"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(fmt(r[c], 3 if isinstance(r[c], float) else 0) for c in cols) + " |")
    (exp_dir / "table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    fig_vision(df, exp_dir / "fig_vision.png")
    fig_views(df, exp_dir / "fig_views.png")
    fig_line(df, exp_dir / "fig_line.png")
    missing = [c for c in order if c not in set(df["condition"])]
    print(f"{len(df)} runs analysed -> {exp_dir / 'table.md'}, fig_vision.png, fig_views.png, fig_line.png")
    if missing:
        print(f"not finished: {', '.join(missing)}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
