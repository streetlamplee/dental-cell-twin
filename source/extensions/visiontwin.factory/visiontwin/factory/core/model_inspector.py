"""Learned inspector for the inspection cell (pure Python + numpy/OpenCV; no Kit, no ONNX).

The model (scripts/train_inspector_model.py) is a multiple-instance network: one shared CNN
scores every view of a product, the product score is the maximum over the views. This fits
defects that only some views show (a chipped margin is invisible from the top), where a
per-view label would be wrong.

This module owns what training and inference must share:
  preprocess()   ROI crop -> INPUT x INPUT, RGB float32, (x - 0.5) / 0.25, CHW
  ModelInspector turns the network outputs into a verdict (label, score, the view that
                 decided), with the threshold from the model card (config/models/*.json)
The network itself is passed in as a callable, so the Kit side can use ONNX Runtime and the
tests a fake. Like VisionInspector, it only ever sees pixels.
"""

import json
import math
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

INPUT = 128
MEAN, STD = 0.5, 0.25

GOOD, DEFECT = "good", "defect"


def preprocess(rgb: np.ndarray, roi: Tuple[int, int, int, int]) -> np.ndarray:
    """HxWx3 uint8 RGB frame -> 3 x INPUT x INPUT float32 network input."""
    x0, y0, x1, y1 = roi
    crop = cv2.resize(np.ascontiguousarray(rgb[y0:y1, x0:x1, :3]), (INPUT, INPUT), interpolation=cv2.INTER_AREA)
    return ((crop.astype(np.float32) / 255.0 - MEAN) / STD).transpose(2, 0, 1)


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


@dataclass
class ModelCard:
    """What the trainer wrote next to the ONNX file."""
    views: List[str]
    roi: Tuple[int, int, int, int]
    threshold: float = 0.5
    input_size: int = INPUT
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str) -> "ModelCard":
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if int(d.get("input_size", INPUT)) != INPUT or d.get("normalize") != [MEAN, STD]:
            raise ValueError(f"{path}: preprocessing does not match core.model_inspector")
        return cls(list(d["views"]), tuple(d["roi"]), float(d.get("threshold", 0.5)), INPUT, d)


@dataclass
class ModelVerdict:
    label: str
    score: float  # P(defect) of the product
    view_scores: List[float]  # P(defect) per view
    decided_by: Optional[str]  # view with the highest score
    latency_ms: float


# Network: (1, V, 3, INPUT, INPUT) float32 -> (product logit, per-view logits[V])
Network = Callable[[np.ndarray], Tuple[float, Sequence[float]]]


class ModelInspector:
    def __init__(self, network: Network, card: ModelCard) -> None:
        self.network = network
        self.card = card

    def judge(self, frames: Sequence[np.ndarray]) -> ModelVerdict:
        """frames: one RGB image per view, in the card's view order."""
        if len(frames) != len(self.card.views):
            raise ValueError(f"expected {len(self.card.views)} views, got {len(frames)}")
        t0 = time.perf_counter()
        batch = np.stack([preprocess(f, self.card.roi) for f in frames])[None]
        logit, view_logits = self.network(batch)
        score = sigmoid(float(logit))
        view_scores = [sigmoid(float(v)) for v in view_logits]
        k = int(np.argmax(view_scores))
        return ModelVerdict(DEFECT if score >= self.card.threshold else GOOD, score, view_scores,
                            self.card.views[k], (time.perf_counter() - t0) * 1000.0)
