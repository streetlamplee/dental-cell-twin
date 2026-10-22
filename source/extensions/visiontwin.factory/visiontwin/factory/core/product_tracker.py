"""Product records and their lifecycle state machine.

SPAWNED -> MOVING -> INSPECTED -> SORTED   -> EXITED   (passed down the line)
                              +-> REJECTED -> EXITED   (pushed into reject bin)

ground_truth is stored for evaluation only. Vision code must never read it.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

GOOD = "good"
DEFECT = "defect"


class ProductState(str, Enum):
    SPAWNED = "SPAWNED"
    MOVING = "MOVING"
    INSPECTED = "INSPECTED"
    SORTED = "SORTED"
    REJECTED = "REJECTED"
    EXITED = "EXITED"


_ALLOWED = {
    ProductState.SPAWNED: {ProductState.MOVING},
    ProductState.MOVING: {ProductState.INSPECTED},
    ProductState.INSPECTED: {ProductState.SORTED, ProductState.REJECTED},
    ProductState.SORTED: {ProductState.EXITED},
    ProductState.REJECTED: {ProductState.EXITED},
    ProductState.EXITED: set(),
}


class InvalidTransition(Exception):
    pass


@dataclass
class Product:
    product_id: int
    ground_truth: str  # GOOD or DEFECT, evaluation only
    defect_kind: Optional[str]  # e.g. "color"; None when GOOD
    x: float
    spawn_time: float
    state: ProductState = ProductState.SPAWNED
    prediction: Optional[str] = None  # set by the inspector (Day 3/4)
    score: Optional[float] = None
    defect_reason: Optional[str] = None  # inspector's reason for a defect verdict ("color", "shape", ...)
    inspected_time: Optional[float] = None  # sim time of the inspection-line crossing
    inspection_start_ms: Optional[float] = None  # wall clock since run start: frame requested
    inspection_end_ms: Optional[float] = None  # wall clock since run start: verdict ready
    late_prediction: Optional[str] = None  # verdict that arrived after sorting (not applied)
    sort_time: Optional[float] = None  # sim time of the reject-line crossing
    sort_speed: Optional[float] = None  # conveyor speed at that moment
    exit_time: Optional[float] = None
    exit_route: Optional[str] = None  # "pass" or "reject"

    @property
    def on_belt(self) -> bool:
        return self.state in (ProductState.SPAWNED, ProductState.MOVING,
                              ProductState.INSPECTED, ProductState.SORTED)


class ProductTracker:
    """Owns all products. IDs are issued here only, so they cannot collide."""

    def __init__(self) -> None:
        self._products: Dict[int, Product] = {}
        self._next_id = 1

    def spawn(self, ground_truth: str, defect_kind: Optional[str], x: float, t: float) -> Product:
        if ground_truth not in (GOOD, DEFECT):
            raise ValueError(f"unknown ground_truth: {ground_truth}")
        p = Product(self._next_id, ground_truth, defect_kind, x, t)
        self._products[p.product_id] = p
        self._next_id += 1
        return p

    def transition(self, product_id: int, new_state: ProductState) -> Product:
        p = self._products[product_id]
        if new_state not in _ALLOWED[p.state]:
            raise InvalidTransition(f"product {product_id}: {p.state.value} -> {new_state.value}")
        p.state = new_state
        return p

    def get(self, product_id: int) -> Product:
        return self._products[product_id]

    def on_belt(self) -> List[Product]:
        return [p for p in self._products.values() if p.on_belt]

    def all(self) -> List[Product]:
        return list(self._products.values())

    def __len__(self) -> int:
        return len(self._products)
