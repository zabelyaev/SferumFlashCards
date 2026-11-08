import math
from datetime import UTC, timedelta
from itertools import chain
from typing import TYPE_CHECKING

from fsrs import Card, Rating, Scheduler
from fsrs.scheduler import (
    DEFAULT_PARAMETERS,
    LOWER_BOUNDS_PARAMETERS,
    UPPER_BOUNDS_PARAMETERS,
)

from application.study.optimization.contracts import HistorySplit

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.study.optimization.contracts import OptimizationReview
    from common.config.study import StudyConfig


MIN_TRAIN_EXAMPLES = 512
MIN_VALIDATION_EXAMPLES = 32
MAX_OPTIMIZER_REVIEWS_PER_CYCLE = 64


def validate_parameters(parameters: Sequence[float]) -> tuple[float, ...]:
    if len(parameters) != len(DEFAULT_PARAMETERS):
        raise ValueError(f"Expected {len(DEFAULT_PARAMETERS)} FSRS parameters.")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not lower <= value <= upper
        for value, lower, upper in zip(
            parameters, LOWER_BOUNDS_PARAMETERS, UPPER_BOUNDS_PARAMETERS
        )
    ):
        raise ValueError(
            "FSRS parameters must be finite numbers within library bounds."
        )
    return tuple(float(value) for value in parameters)


def optimizer_training_reviews(
    reviews: Sequence[OptimizationReview],
) -> tuple[OptimizationReview, ...]:
    """Match fsrs 6.3.2's stable per-cycle prefix without trimming replay history."""
    counts: dict[int, int] = {}
    selected: list[OptimizationReview] = []
    for review in sorted(reviews, key=lambda item: (item.reviewed_at, item.review_id)):
        count = counts.get(review.cycle_id, 0)
        if count < MAX_OPTIMIZER_REVIEWS_PER_CYCLE:
            selected.append(review)
            counts[review.cycle_id] = count + 1
    return tuple(selected)


def split_history(reviews: Sequence[OptimizationReview]) -> HistorySplit:
    ordered = sorted(reviews, key=lambda review: (review.reviewed_at, review.review_id))
    if not ordered:
        return HistorySplit((), (), 0)

    cutoff = ordered[len(ordered) * 4 // 5].reviewed_at
    train = tuple(review for review in ordered if review.reviewed_at < cutoff)
    validation = tuple(review for review in ordered if review.reviewed_at >= cutoff)
    previous: dict[int, OptimizationReview] = {}
    examples = 0
    for review in optimizer_training_reviews(train):
        prior = previous.get(review.cycle_id)
        if prior is not None and (review.reviewed_at - prior.reviewed_at).days > 0:
            examples += 1
        previous[review.cycle_id] = review
    return HistorySplit(train, validation, examples)


def validation_loss(
    split: HistorySplit,
    parameters: Sequence[float],
    config: StudyConfig,
) -> tuple[float | None, int]:
    scheduler = Scheduler(
        parameters=validate_parameters(parameters),
        desired_retention=config.desired_retention,
        learning_steps=(timedelta(seconds=config.learning_step_seconds),),
        relearning_steps=(timedelta(seconds=config.relearning_step_seconds),),
        maximum_interval=config.maximum_interval,
        enable_fuzzing=False,
    )
    cards: dict[int, Card] = {}
    validation_cycles = {review.cycle_id for review in split.validation}
    loss = 0.0
    examples = 0
    for review, is_validation in chain(
        (
            (review, False)
            for review in split.train
            if review.cycle_id in validation_cycles
        ),
        ((review, True) for review in split.validation),
    ):
        when = review.reviewed_at.astimezone(UTC)
        card = cards.get(review.cycle_id)
        if card is None:
            card = Card(card_id=review.cycle_id, due=when)
        if is_validation and card.last_review and (when - card.last_review).days > 0:
            probability = float(scheduler.get_card_retrievability(card, when))
            if not math.isfinite(probability):
                raise ValueError("Non-finite FSRS prediction.")
            probability = min(1 - 1e-15, max(1e-15, probability))
            loss -= (
                math.log1p(-probability)
                if review.rating == 1
                else math.log(probability)
            )
            examples += 1
        card, _ = scheduler.review_card(
            card, Rating(review.rating), review_datetime=when
        )
        cards[review.cycle_id] = card
    return (loss / examples if examples else None), examples
