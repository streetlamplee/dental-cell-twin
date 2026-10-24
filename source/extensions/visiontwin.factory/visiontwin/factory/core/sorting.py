"""Reject-line decisions keyed by product ID (pure Python).

At the reject line the controller looks up the prediction stored on THAT product
object, so a result can never be applied to a different product. Rules:

  prediction == "defect"  -> reject
  prediction == "good"    -> pass
  prediction == "unknown" -> unknown_policy (default reject = quarantine, fail-safe)
  no prediction yet       -> unknown_policy, reason "no result at reject line"

A result that arrives after its product was sorted is recorded as late and ignored.

With inspection switched off (setting `vision = false`) nothing is judged: every product
passes, with the reason "no inspection (vision off)".
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

PASS = "pass"
REJECT = "reject"

EXPECTED_ROUTE = {"good": PASS, "defect": REJECT}


@dataclass
class SortDecision:
    product_id: int
    route: str  # PASS or REJECT
    reason: str
    prediction: Optional[str]  # prediction seen at the reject line (None = not arrived)


class SortingController:
    def __init__(self, unknown_policy: str = REJECT, inspection: bool = True) -> None:
        if unknown_policy not in (PASS, REJECT):
            raise ValueError(f"unknown_policy must be {PASS!r} or {REJECT!r}")
        self.unknown_policy = unknown_policy
        self.inspection = inspection
        self.decisions: Dict[int, SortDecision] = {}
        self.late_results: List[int] = []

    def decide(self, product) -> bool:
        """ConveyorSim reject_decider: True = push the product off at the reject line."""
        pid = product.product_id
        if pid in self.decisions:
            raise RuntimeError(f"product {pid} reached the reject line twice")
        pred = product.prediction
        if not self.inspection:
            route, reason = PASS, "no inspection (vision off)"
        elif pred == "defect":
            route, reason = REJECT, "predicted defect"
        elif pred == "good":
            route, reason = PASS, "predicted good"
        elif pred == "unknown":
            route, reason = self.unknown_policy, "prediction unknown (fail-safe)"
        else:
            route, reason = self.unknown_policy, "no result at reject line (fail-safe)"
        self.decisions[pid] = SortDecision(pid, route, reason, pred)
        return route == REJECT

    def is_sorted(self, product_id: int) -> bool:
        return product_id in self.decisions

    def record_late(self, product_id: int) -> None:
        self.late_results.append(product_id)

    @staticmethod
    def route_correct(ground_truth: str, route: str) -> bool:
        return EXPECTED_ROUTE.get(ground_truth) == route
