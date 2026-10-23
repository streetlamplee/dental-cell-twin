"""Train the inspection cell's learned inspector on synthetic data (system Python + PyTorch).

Input: a dataset from scripts/generate_dataset.ps1 (labels.csv, dataset.json, Replicator
frames). Every product sample has one frame per view; preprocessing is core.model_inspector.
preprocess (the same function the Kit extension uses).

Model: multiple-instance CNN. A small shared CNN (4 conv blocks, global average pooling)
scores every view; the product logit is the maximum over the views. Trained with BCE on the
product label only (a chip's top view is not labelled "defect").

Split: samples with id % 5 == 0 are validation (20 %), never used for training. The line runs
(seed 42) used for the final evaluation are not in the dataset at all.

Outputs:
  <out>.onnx   input "views" (1, V, 3, 128, 128) -> "defect_logit" (1), "view_logits" (1, V)
  <out>.json   model card: views, ROI, preprocessing, threshold, dataset hash, validation metrics
  <report_dir>/train_report.json, fig_training.png

Usage: python scripts/train_inspector_model.py <dataset_dir> <out_without_ext> <report_dir> [epochs]
"""

import csv
import hashlib
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/extensions/visiontwin.factory/visiontwin/factory"))

from core.model_inspector import INPUT, MEAN, STD, preprocess  # noqa: E402

SEED = 0
SURFACE, TEXT, TEXT2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


class MilNet(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        chans, layers = [3, 32, 64, 96, 128], []
        for a, b in zip(chans, chans[1:]):
            layers += [nn.Conv2d(a, b, 3, padding=1, bias=False), nn.BatchNorm2d(b), nn.ReLU(inplace=True),
                       nn.Conv2d(b, b, 3, padding=1, bias=False), nn.BatchNorm2d(b), nn.ReLU(inplace=True),
                       nn.MaxPool2d(2)]
        self.backbone = nn.Sequential(*layers, nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Dropout(0.2), nn.Linear(128, 1))

    def forward(self, views):  # (B, V, 3, H, W)
        b, v = views.shape[0], views.shape[1]
        view_logits = self.backbone(views.reshape(b * v, *views.shape[2:])).reshape(b, v)
        return view_logits.max(dim=1).values, view_logits


def load(dataset: Path):
    meta = json.loads((dataset / "dataset.json").read_text(encoding="utf-8"))
    roi = tuple(meta["roi"])
    with open(dataset / "labels.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    n_views = len(meta["views"])
    samples = {}
    for r in rows:
        samples.setdefault(int(r["sample"]), []).append(r)
    ids = sorted(samples)
    x = np.zeros((len(ids), n_views, 3, INPUT, INPUT), np.float16)
    y = np.zeros(len(ids), np.float32)
    kinds = []
    for i, sid in enumerate(ids):
        views = sorted(samples[sid], key=lambda r: int(r["view"]))
        for r in views:
            rgb = cv2.cvtColor(cv2.imread(str(dataset / r["file"])), cv2.COLOR_BGR2RGB)
            x[i, int(r["view"])] = preprocess(rgb, roi)
        y[i] = 1.0 if views[0]["ground_truth"] == "defect" else 0.0
        kinds.append(views[0]["defect_kind"] or "good")
    labels_hash = hashlib.sha256((dataset / "labels.csv").read_bytes()).hexdigest()
    return meta, np.array(ids), x, y, np.array(kinds), labels_hash


def evaluate(model, x, y, kinds, device):
    model.eval()
    logits, top = [], []
    with torch.no_grad():
        for i in range(0, len(x), 64):
            lg, vl = model(torch.from_numpy(x[i:i + 64].astype(np.float32)).to(device))
            logits.append(lg.cpu().numpy())
            top.append(vl[:, 0].cpu().numpy())
    pred = np.concatenate(logits) >= 0.0
    pred_top = np.concatenate(top) >= 0.0
    gt = y >= 0.5
    def stats(p):
        tp, fp = int((p & gt).sum()), int((p & ~gt).sum())
        fn, tn = int((~p & gt).sum()), int((~p & ~gt).sum())
        out = {"TP": tp, "FP": fp, "FN": fn, "TN": tn, "accuracy": float((p == gt).mean()),
               "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None}
        for k in sorted(set(kinds) - {"good"}):
            sel = kinds == k
            out[f"recall_{k}"] = float(p[sel].mean()) if sel.any() else None
        return out
    return stats(pred), stats(pred_top)


def main() -> int:
    if len(sys.argv) not in (4, 5):
        print(__doc__)
        return 2
    dataset, out, report_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    epochs = int(sys.argv[4]) if len(sys.argv) == 5 else 20
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    t0 = time.time()
    meta, ids, x, y, kinds, labels_hash = load(dataset)
    val = ids % 5 == 0
    print(f"dataset {dataset.name}: {len(ids)} samples ({int(y.sum())} defect), views {meta['views']}, "
          f"train {int((~val).sum())} / val {int(val.sum())}, loaded in {time.time() - t0:.0f}s, device {device}")

    model = MilNet().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    loss_fn = nn.BCEWithLogitsLoss()
    xt, yt = x[~val], y[~val]
    history = []
    for ep in range(epochs):
        model.train()
        order = np.random.permutation(len(xt))
        total = 0.0
        for i in range(0, len(order), 16):
            idx = order[i:i + 16]
            xb = torch.from_numpy(xt[idx].astype(np.float32)).to(device)
            gain = torch.empty(len(idx), 1, 1, 1, 1, device=device).uniform_(0.85, 1.15)  # mild exposure jitter
            xb = (((xb * STD + MEAN) * gain).clamp(0, 1) - MEAN) / STD
            logit, _ = model(xb)
            loss = loss_fn(logit, torch.from_numpy(yt[idx]).to(device))
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item() * len(idx)
        sched.step()
        v, _ = evaluate(model, x[val], y[val], kinds[val], device)
        history.append({"epoch": ep + 1, "train_loss": total / len(xt), "val_accuracy": v["accuracy"]})
        print(f"epoch {ep + 1:2d}: loss {total / len(xt):.4f}, val accuracy {v['accuracy']:.3f}")
    val_all, val_top = evaluate(model, x[val], y[val], kinds[val], device)
    print(f"validation (all views): {val_all}")
    print(f"validation (top view only, same network): {val_top}")

    model.eval().cpu()
    dummy = torch.from_numpy(x[val][:1].astype(np.float32))
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(model, (dummy,), str(out.with_suffix(".onnx")), input_names=["views"],
                      output_names=["defect_logit", "view_logits"], opset_version=17, dynamo=False)
    import onnxruntime as ort

    sess = ort.InferenceSession(str(out.with_suffix(".onnx")), providers=["CPUExecutionProvider"])
    check = torch.from_numpy(x[val][:8].astype(np.float32))
    diffs = []
    for i in range(len(check)):
        with torch.no_grad():
            ref, ref_v = model(check[i:i + 1])
        o, o_v = sess.run(None, {"views": check[i:i + 1].numpy()})
        diffs.append(max(abs(float(ref[0]) - float(o[0])), float(np.abs(ref_v.numpy() - o_v).max())))
    print(f"onnx vs torch max |diff| over 8 samples: {max(diffs):.2e}")

    card = {"name": out.stem, "views": meta["views"], "roi": meta["roi"], "input_size": INPUT,
            "normalize": [MEAN, STD], "threshold": 0.5, "architecture": "MilNet: shared 4-block CNN, max over views",
            "dataset": {"dir": dataset.name, "labels_sha256": labels_hash, "samples": len(ids),
                        "light_range": meta["light_range"], "replicator": meta.get("replicator")},
            "split": "validation = sample id % 5 == 0", "epochs": epochs, "seed": SEED, "torch": torch.__version__,
            "validation_all_views": val_all, "validation_top_view_only": val_top,
            "onnx_max_abs_diff": max(diffs), "train_seconds": round(time.time() - t0, 1)}
    out.with_suffix(".json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "train_report.json").write_text(json.dumps({**card, "history": history}, indent=2), encoding="utf-8")
    figure(history, report_dir / "fig_training.png")
    print(f"model -> {out.with_suffix('.onnx')} (+ .json), report -> {report_dir}")
    return 0


def figure(history, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ep = [h["epoch"] for h in history]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.2), facecolor=SURFACE)
    for ax, key, title in ((axes[0], "train_loss", "Training loss (BCE)"), (axes[1], "val_accuracy", "Validation accuracy")):
        ax.set_facecolor(SURFACE)
        ax.plot(ep, [h[key] for h in history], color="#2a78d6", linewidth=2)
        ax.set_title(title, color=TEXT, fontsize=11, loc="left")
        ax.tick_params(colors=TEXT2, labelsize=9)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(GRID)
        ax.set_xlabel("epoch", color=TEXT2, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
