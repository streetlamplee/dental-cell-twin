"""Evaluation metrics (pure Python). "defect" is the positive class.

Unknown predictions are reported separately. For precision/recall they count as
"not flagged": a defect predicted unknown is a false negative (missed), a good
product predicted unknown is not a false positive.
"""

import math
from typing import Dict, Iterable, List, Optional, Sequence

POSITIVE = "defect"
UNKNOWN = "unknown"


def confusion(ground_truth: Sequence[str], predicted: Sequence[str]) -> Dict[str, int]:
    if len(ground_truth) != len(predicted):
        raise ValueError("length mismatch")
    c = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "unknown": 0, "n": len(predicted)}
    for gt, pr in zip(ground_truth, predicted):
        if pr == UNKNOWN:
            c["unknown"] += 1
        pos_gt, pos_pr = gt == POSITIVE, pr == POSITIVE
        if pos_gt and pos_pr:
            c["tp"] += 1
        elif pos_gt:
            c["fn"] += 1
        elif pos_pr:
            c["fp"] += 1
        else:
            c["tn"] += 1
    return c


def _ratio(num: int, den: int) -> Optional[float]:
    return None if den == 0 else num / den


def precision_recall_f1(c: Dict[str, int]):
    p = _ratio(c["tp"], c["tp"] + c["fp"])
    r = _ratio(c["tp"], c["tp"] + c["fn"])
    f1 = None if p is None or r is None or (p + r) == 0 else 2 * p * r / (p + r)
    return p, r, f1


def accuracy(ground_truth: Sequence[str], predicted: Sequence[str]) -> Optional[float]:
    if not predicted:
        return None
    return sum(g == p for g, p in zip(ground_truth, predicted)) / len(predicted)


def percentile(values: Iterable[float], q: float) -> Optional[float]:
    """Linear-interpolated percentile (q in 0..100), like numpy's default."""
    xs: List[float] = sorted(values)
    if not xs:
        return None
    k = (len(xs) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def fmt(x: Optional[float], digits: int = 3) -> str:
    return "N/A" if x is None else f"{x:.{digits}f}"
