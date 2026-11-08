from dataclasses import dataclass
from datetime import datetime
from typing import Literal

type OptimizationStatus = Literal[
    "updated", "insufficient_data", "not_improved", "already_running", "failed"
]


@dataclass(frozen=True)
class OptimizationReview:
    cycle_id: int
    rating: int
    reviewed_at: datetime
    review_id: int


@dataclass(frozen=True)
class OptimizationHistory:
    parameters: tuple[float, ...] | None
    reviews: tuple[OptimizationReview, ...]
    incompatible_cycles: int = 0


@dataclass(frozen=True)
class OptimizationResult:
    user_id: int
    status: OptimizationStatus
    message: str = ""
    train_reviews: int = 0
    validation_reviews: int = 0
    current_loss: float | None = None
    candidate_loss: float | None = None


@dataclass(frozen=True)
class HistorySplit:
    train: tuple[OptimizationReview, ...]
    validation: tuple[OptimizationReview, ...]
    train_examples: int
