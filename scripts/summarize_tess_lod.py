"""Summarise the tessellation LOD comparison written by compare_tess_lod.ps1.

Reads results/cad_lod/<asset>/lod<n>.usd.report.json and writes
  results/cad_lod/<asset>/table.md   one row per LOD
  results/cad_lod/lod_compare.png    triangles and |volume error| per LOD, one line per asset

Usage: python scripts/summarize_tess_lod.py <results/cad_lod>
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Chart tokens (dataviz reference palette, light mode), same as analyze_results.py.
SURFACE, TEXT, TEXT2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
ASSET_COLOR = {"teeth_mill": "#2a78d6", "kfl08": "#eb6834", "dental_crown": "#1baf7a"}  # slots 1, 2, 3
ASSET_NAME = {"teeth_mill": "Milling machine", "kfl08": "KFL08 bearing", "dental_crown": "Dental crown"}


def load(asset_dir: Path):
    rows = []
    for f in sorted(asset_dir.glob("lod*.usd.report.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        rows.append({"lod": int(r["convert"]["options"]["tessLOD"]), "triangles": r["usd_mesh"]["triangles"],
                     "vol_err": r["volume_error_pct"], "area_err": r["area_error_pct"],
                     "size_diff": max(abs(d) for d in r["size_diff_mm"]), "kib": r["file_bytes"] / 1024,
                     "seconds": r["convert"]["seconds"]})
    return sorted(rows, key=lambda r: r["lod"])


def write_table(asset_dir: Path, rows):
    lines = ["| LOD | triangles | volume error % | area error % | max size diff mm | file KiB | convert s |",
             "|---|---|---|---|---|---|---|"]
    lines += [f"| {r['lod']} | {r['triangles']} | {r['vol_err']:+.3f} | {r['area_err']:+.3f} | "
              f"{r['size_diff']:.3f} | {r['kib']:.0f} | {r['seconds']:.1f} |" for r in rows]
    (asset_dir / "table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"## {asset_dir.name}\n" + "\n".join(lines))


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
    ax.set_xticks(range(5))
    ax.set_xlabel("HOOPS tessLOD (0 extra low ... 4 extra high)", color=TEXT2, fontsize=9)


def main():
    root = Path(sys.argv[1])
    data = {d.name: load(d) for d in sorted(root.iterdir()) if d.is_dir()}
    data = {k: v for k, v in data.items() if v}
    for name, rows in data.items():
        write_table(root / name, rows)
    order = [a for a in ASSET_COLOR if a in data] + [a for a in data if a not in ASSET_COLOR]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), facecolor=SURFACE)
    panels = (("triangles", "Triangles (log scale)"), ("vol_err", "|Volume error| vs STEP B-rep, % (log scale)"))
    for ax, (key, title) in zip(axes, panels):
        style(ax, title)
        ax.set_yscale("log")
        for name in order:
            rows = data[name]
            ys = [abs(r[key]) for r in rows]
            ax.plot([r["lod"] for r in rows], ys, color=ASSET_COLOR.get(name, TEXT2), linewidth=2, marker="o",
                    markersize=7, markeredgecolor=SURFACE, markeredgewidth=2, label=ASSET_NAME.get(name, name))
            ax.annotate(f"{ys[-1]:,.0f}" if key == "triangles" else f"{ys[-1]:.3g} %",(rows[-1]["lod"], ys[-1]), textcoords="offset points", xytext=(6, 0),
                        va="center", color=TEXT2, fontsize=8)
    axes[0].legend(frameon=False, fontsize=9, labelcolor=TEXT)
    fig.suptitle("STEP -> USD (Omniverse CAD converter): tessellation level vs accuracy", color=TEXT, fontsize=12,
                 x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(root / "lod_compare.png", dpi=150, facecolor=SURFACE)
    print(f"figure: {root / 'lod_compare.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
