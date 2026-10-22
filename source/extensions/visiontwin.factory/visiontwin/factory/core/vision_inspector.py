"""Rule-based color inspection on an RGB image (OpenCV + NumPy, no Kit).

The inspector only ever sees pixels (and an optional ROI from camera calibration).
It never receives product IDs or ground truth.

Method
1. Restrict to the ROI (belt lane).
2. Foreground = saturated, not-too-dark pixels (the belt and floor are grey).
3. Product = largest connected foreground blob above `min_area_px`.
4. Colour check: score = fraction of blob pixels whose hue is within `hue_tolerance`
   of the reference ("golden sample") hue; score < good_ratio_min -> colour defect.
5. Shape check (optional, `interior_bright_min` set): fill the blob's outer contour;
   interior = filled - blob (bores, holes, inserts: the unsaturated inside of the part).
   interior_bright = fraction of interior pixels with V >= `bright_v_min`. A bearing
   insert shows bright rings, an empty bore shows the dark belt/shadow ->
   interior_bright < interior_bright_min -> shape (missing part) defect.
6. No blob -> unknown (never guess). Any failed check -> defect, reason lists them.
"""

import json
import time
from dataclasses import asdict, dataclass, field, fields
from typing import Optional, Tuple

import cv2
import numpy as np

GOOD = "good"
DEFECT = "defect"
UNKNOWN = "unknown"


@dataclass
class InspectorConfig:
    roi: Optional[Tuple[int, int, int, int]] = None  # x0, y0, x1, y1; None = full image
    sat_min: int = 80  # 0..255
    val_min: int = 40  # 0..255
    min_area_px: int = 400
    reference_hue: float = 105.0  # OpenCV hue 0..179 of a good product
    hue_tolerance: float = 12.0
    good_ratio_min: float = 0.85
    # Shape check (None = off, as for the box product)
    interior_bright_min: Optional[float] = None
    bright_v_min: int = 140

    @classmethod
    def load(cls, path: str) -> "InspectorConfig":
        """Load from JSON; unknown keys are ignored, missing keys keep defaults."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        known = {f.name for f in fields(cls)}
        cfg = cls(**{k: v for k, v in data.items() if k in known})
        if cfg.roi is not None:
            cfg.roi = tuple(cfg.roi)
        return cfg

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)


@dataclass
class InspectionResult:
    label: str
    score: float  # fraction of blob pixels matching the reference hue (0..1)
    area_px: int
    mean_hue: float  # circular mean of blob hue, OpenCV scale; NaN if no blob
    bbox: Optional[Tuple[int, int, int, int]]  # x, y, w, h in full-image coordinates
    latency_ms: float
    reason: str
    params: dict = field(default_factory=dict)
    defect_reason: str = ""  # "", "color", "shape" or "color+shape"
    interior_ratio: float = float("nan")  # interior area / filled silhouette area
    interior_bright: float = float("nan")  # bright fraction of the interior


def hue_distance(h: np.ndarray, ref: float) -> np.ndarray:
    """Circular distance on OpenCV's 0..179 hue scale."""
    d = np.abs(h.astype(np.float32) - ref)
    return np.minimum(d, 180.0 - d)


def circular_mean_hue(h: np.ndarray) -> float:
    ang = h.astype(np.float32) * (2 * np.pi / 180.0)
    mean = np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())
    return float((mean % (2 * np.pi)) * 180.0 / (2 * np.pi))


class VisionInspector:
    def __init__(self, config: Optional[InspectorConfig] = None) -> None:
        self.config = config or InspectorConfig()

    def inspect(self, rgb: np.ndarray) -> InspectionResult:
        t0 = time.perf_counter()
        c = self.config
        if rgb.ndim != 3 or rgb.shape[2] < 3:
            raise ValueError(f"expected HxWx3 RGB image, got {rgb.shape}")
        rgb = np.ascontiguousarray(rgb[:, :, :3])

        x0, y0, x1, y1 = c.roi if c.roi else (0, 0, rgb.shape[1], rgb.shape[0])
        hsv = cv2.cvtColor(rgb[y0:y1, x0:x1], cv2.COLOR_RGB2HSV)
        mask = ((hsv[:, :, 1] >= c.sat_min) & (hsv[:, :, 2] >= c.val_min)).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        params = {"roi": (x0, y0, x1, y1), "reference_hue": c.reference_hue,
                  "hue_tolerance": c.hue_tolerance, "good_ratio_min": c.good_ratio_min}
        if n <= 1:
            return self._result(UNKNOWN, 0.0, 0, float("nan"), None, t0, "no foreground in ROI", params)

        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area < c.min_area_px:
            return self._result(UNKNOWN, 0.0, area, float("nan"), None, t0,
                                f"largest blob {area}px < min_area {c.min_area_px}px", params)

        blob = labels == idx
        hues = hsv[:, :, 0][blob]
        score = float((hue_distance(hues, c.reference_hue) <= c.hue_tolerance).mean())
        bx, by, bw, bh = (int(v) for v in stats[idx, :4])
        bbox = (bx + x0, by + y0, bw, bh)
        color_ok = score >= c.good_ratio_min
        reasons = [f"hue match {score:.2f} {'>=' if color_ok else '<'} {c.good_ratio_min}"]
        failed = [] if color_ok else ["color"]

        interior_ratio = interior_bright = float("nan")
        if c.interior_bright_min is not None:
            interior_ratio, interior_bright = self._interior(blob, hsv[:, :, 2], c.bright_v_min)
            shape_ok = interior_bright >= c.interior_bright_min
            reasons.append(f"interior bright {interior_bright:.2f} {'>=' if shape_ok else '<'} "
                           f"{c.interior_bright_min} (interior {interior_ratio:.2f})")
            if not shape_ok:
                failed.append("shape")
            params["interior_bright_min"] = c.interior_bright_min

        label = DEFECT if failed else GOOD
        res = self._result(label, score, area, circular_mean_hue(hues), bbox, t0, "; ".join(reasons), params)
        res.defect_reason = "+".join(failed)
        res.interior_ratio, res.interior_bright = interior_ratio, interior_bright
        return res

    @staticmethod
    def _interior(blob: np.ndarray, value: np.ndarray, bright_v_min: int):
        """Interior of the blob's outer contour that is not blob (holes, bores, inserts)."""
        contours, _ = cv2.findContours(blob.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filled = np.zeros(blob.shape, np.uint8)
        cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)
        interior = (filled > 0) & ~blob
        n_interior, n_filled = int(interior.sum()), int((filled > 0).sum())
        if n_interior == 0:
            return 0.0, 0.0
        bright = float((value[interior] >= bright_v_min).mean())
        return n_interior / max(n_filled, 1), bright

    @staticmethod
    def _result(label, score, area, mean_hue, bbox, t0, reason, params) -> InspectionResult:
        latency = (time.perf_counter() - t0) * 1000.0
        return InspectionResult(label, score, area, mean_hue, bbox, latency, reason, params)
