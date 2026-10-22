"""Which product geometry to spawn for a given ground truth (pure Python).

"box" keeps the original procedural cube. Real CAD parts come from
assets/parts/catalog.json; each variant is a USD layer built by make_part_variants.
The ground truth decides the variant; nothing downstream may read the variant back
(the inspector only gets pixels).
"""

import json
import os
from typing import Optional, Tuple

BOX = "box"


class ProductCatalog:
    def __init__(self, part: str = BOX, parts_dir: Optional[str] = None) -> None:
        self.part = part
        self.parts_dir = parts_dir
        self._variants = {}  # (ground_truth, defect_kind) -> usd path
        if part != BOX:
            if not parts_dir:
                raise ValueError("parts_dir is required for CAD parts")
            with open(os.path.join(parts_dir, "catalog.json"), encoding="utf-8") as f:
                spec = json.load(f)[part]
            for name, v in spec["variants"].items():
                path = os.path.join(parts_dir, "usd", f"{part}_{name}.usda")
                self._variants[(v["ground_truth"], v["defect_kind"])] = path

    @property
    def is_box(self) -> bool:
        return self.part == BOX

    @property
    def defect_kinds(self) -> Tuple[str, ...]:
        if self.is_box:
            return ("color",)
        return tuple(sorted(k for (gt, k) in self._variants if gt == "defect"))

    def variant_path(self, ground_truth: str, defect_kind: Optional[str]) -> Optional[str]:
        """USD layer for this product, or None for the procedural box."""
        if self.is_box:
            return None
        key = (ground_truth, defect_kind if ground_truth == "defect" else None)
        if key not in self._variants:
            raise KeyError(f"{self.part}: no variant for {key}")
        return self._variants[key]
