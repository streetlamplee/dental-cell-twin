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

Options for white/unsaturated products (dental crowns, Day 7):
- segment="bright": foreground = pixels at least `bright_delta` brighter (Lab L) than the
  belt, estimated as the median L of the ROI border; excludes the darker cast shadow.
- color_metric="ab": score = fraction of blob pixels within `ab_tolerance` of `reference_ab`
  in Lab a*b* (shade, largely independent of brightness).
- golden contour: the filled silhouette's outer contour is compared with the calibrated good
  sample: cv2.matchShapes distance > `shape_dist_max` or |area/golden_area - 1| >
  `area_ratio_tol` -> shape defect (e.g. an unmilled corner of the blank).
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
    # Segmentation / colour metric (defaults keep the original box behaviour)
    segment: str = "saturation"  # "saturation" | "bright"
    bright_delta: float = 25.0  # Lab L units (OpenCV 0..255 scale) above the belt
    color_metric: str = "hue"  # "hue" | "ab"
    reference_ab: Optional[Tuple[float, float]] = None  # OpenCV Lab a, b (128 = neutral)
    ab_tolerance: float = 8.0
    # Golden-contour shape check (None = off)
    golden_contour: Optional[list] = None  # [[x, y], ...] outer contour of a good sample
    golden_area_px: Optional[float] = None
    shape_dist_max: Optional[float] = None
    area_ratio_tol: Optional[float] = None

    @classmethod
    def load(cls, path: str) -> "InspectorConfig":
        """Load from JSON; unknown keys are ignored, missing keys keep defaults."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        known = {f.name for f in fields(cls)}
        cfg = cls(**{k: v for k, v in data.items() if k in known})
        if cfg.roi is not None:
            cfg.roi = tuple(cfg.roi)
        if cfg.reference_ab is not None:
            cfg.reference_ab = tuple(cfg.reference_ab)
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
    shape_dist: float = float("nan")  # cv2.matchShapes distance to the golden contour
    area_ratio: float = float("nan")  # filled silhouette area / golden area
    contour: Optional[list] = None  # outer contour (ROI coordinates) of the product, for calibration


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
        crop = rgb[y0:y1, x0:x1]
        hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
        lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB) if (c.segment == "bright" or c.color_metric == "ab") else None
        if c.segment == "bright":
            light = lab[:, :, 0].astype(np.float32)
            border = np.concatenate([light[0], light[-1], light[:, 0], light[:, -1]])
            mask = (light >= float(np.median(border)) + c.bright_delta).astype(np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        else:
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
        if c.color_metric == "ab" and c.reference_ab is not None:
            ab = lab[:, :, 1:3][blob].astype(np.float32)
            dist = np.linalg.norm(ab - np.array(c.reference_ab, np.float32), axis=1)
            score = float((dist <= c.ab_tolerance).mean())
            metric = "ab match"
        else:
            score = float((hue_distance(hues, c.reference_hue) <= c.hue_tolerance).mean())
            metric = "hue match"
        bx, by, bw, bh = (int(v) for v in stats[idx, :4])
        bbox = (bx + x0, by + y0, bw, bh)
        color_ok = score >= c.good_ratio_min
        reasons = [f"{metric} {score:.2f} {'>=' if color_ok else '<'} {c.good_ratio_min}"]
        failed = [] if color_ok else ["color"]

        contour = self._outer_contour(blob)
        shape_dist = area_ratio = float("nan")
        if c.golden_contour is not None and contour is not None:
            golden = np.array(c.golden_contour, np.int32).reshape(-1, 1, 2)
            shape_dist = float(cv2.matchShapes(contour, golden, cv2.CONTOURS_MATCH_I1, 0.0))
            area_ratio = float(cv2.contourArea(contour) / max(c.golden_area_px or cv2.contourArea(golden), 1.0))
            dist_ok = c.shape_dist_max is None or shape_dist <= c.shape_dist_max
            area_ok = c.area_ratio_tol is None or abs(area_ratio - 1.0) <= c.area_ratio_tol
            reasons.append(f"contour dist {shape_dist:.3f} (max {c.shape_dist_max}), "
                           f"area ratio {area_ratio:.2f} (tol {c.area_ratio_tol})")
            if not (dist_ok and area_ok) and "shape" not in failed:
                failed.append("shape")

        interior_ratio = interior_bright = float("nan")
        if c.interior_bright_min is not None:
            interior_ratio, interior_bright = self._interior(blob, hsv[:, :, 2], c.bright_v_min)
            shape_ok = interior_bright >= c.interior_bright_min
            reasons.append(f"interior bright {interior_bright:.2f} {'>=' if shape_ok else '<'} "
                           f"{c.interior_bright_min} (interior {interior_ratio:.2f})")
            if not shape_ok and "shape" not in failed:
                failed.append("shape")
            params["interior_bright_min"] = c.interior_bright_min

        label = DEFECT if failed else GOOD
        res = self._result(label, score, area, circular_mean_hue(hues), bbox, t0, "; ".join(reasons), params)
        res.defect_reason = "+".join(failed)
        res.interior_ratio, res.interior_bright = interior_ratio, interior_bright
        res.shape_dist, res.area_ratio = shape_dist, area_ratio
        res.contour = contour.reshape(-1, 2).tolist() if contour is not None else None
        return res

    @staticmethod
    def _outer_contour(blob: np.ndarray):
        contours, _ = cv2.findContours(blob.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return max(contours, key=cv2.contourArea) if contours else None

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
