"""Which product geometry to spawn for a given ground truth (pure Python).

"box" keeps the original procedural cube. CAD parts come from assets/parts/catalog.json;
each variant is a USD layer built by make_part_variants. Processed parts (dental crown)
also have a "raw" layer shown before processing. The ground truth decides the variant;
nothing downstream may read the variant back (the inspector only gets pixels).
"""

import json
import os
from dataclasses import dataclass
from typing import Optional, Tuple

BOX = "box"


@dataclass(frozen=True)
class CameraSpec:
    height_above_belt: float
    focal_mm: float


class ProductCatalog:
    def __init__(self, part: str = BOX, parts_dir: Optional[str] = None) -> None:
        self.part = part
        self.parts_dir = parts_dir
        self._spec = {}
        self._variants = {}  # (ground_truth, defect_kind) -> (raw path | None, final path)
        if part != BOX:
            if not parts_dir:
                raise ValueError("parts_dir is required for CAD parts")
            with open(os.path.join(parts_dir, "catalog.json"), encoding="utf-8") as f:
                self._spec = json.load(f)[part]
            for name, v in self._spec["variants"].items():
                usd = os.path.join(parts_dir, "usd")
                raw = os.path.join(usd, f"{part}_{name}_raw.usda") if "raw" in v else None
                self._variants[(v["ground_truth"], v["defect_kind"])] = (raw, os.path.join(usd, f"{part}_{name}.usda"))

    @property
    def is_box(self) -> bool:
        return self.part == BOX

    @property
    def defect_kinds(self) -> Tuple[str, ...]:
        if self.is_box:
            return ("color",)
        return tuple(sorted(k for (gt, k) in self._variants if gt == "defect"))

    @property
    def process(self) -> Optional[Tuple[str, float]]:
        """(station name, cycle seconds) for processed parts, else None."""
        p = self._spec.get("process")
        return (p["station"], float(p["cycle_s"])) if p else None

    @property
    def spawn_interval(self) -> Optional[float]:
        v = self._spec.get("spawn_interval_s")
        return float(v) if v is not None else None

    @property
    def camera(self) -> Optional[CameraSpec]:
        c = self._spec.get("camera")
        return CameraSpec(float(c["height_above_belt"]), float(c["focal_mm"])) if c else None

    def _key(self, ground_truth: str, defect_kind: Optional[str]):
        key = (ground_truth, defect_kind if ground_truth == "defect" else None)
        if key not in self._variants:
            raise KeyError(f"{self.part}: no variant for {key}")
        return key

    def variant_path(self, ground_truth: str, defect_kind: Optional[str]) -> Optional[str]:
        """Final-shape USD layer for this product, or None for the procedural box."""
        if self.is_box:
            return None
        return self._variants[self._key(ground_truth, defect_kind)][1]

    def raw_path(self, ground_truth: str, defect_kind: Optional[str]) -> Optional[str]:
        """Shape before processing (e.g. the milling blank), or None if not processed."""
        if self.is_box:
            return None
        return self._variants[self._key(ground_truth, defect_kind)][0]
