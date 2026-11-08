import json
import math
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from functools import partial
from importlib.metadata import version
from unittest.mock import AsyncMock, MagicMock

import pytest
from fsrs import Card, Rating, Scheduler
from fsrs.scheduler import DEFAULT_PARAMETERS

from application.study.optimization.contracts import (
    HistorySplit,
    OptimizationHistory,
    OptimizationReview,
)
from application.study.optimization.engine import FsrsOptimizer
from application.study.optimization.quality import (
    optimizer_training_reviews,
    split_history,
    validate_parameters,
    validation_loss,
)
from application.study.optimization.service import FsrsOptimizationService
from common.config.study import StudyConfig


def make_history(cycles: int = 200, days: int = 5) -> tuple[OptimizationReview, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        OptimizationReview(
            cycle_id=cycle,
            rating=1 if (cycle + day) % 5 == 0 else 3,
            reviewed_at=start + timedelta(days=day, seconds=cycle),
            review_id=day * cycles + cycle,
        )
        for day in range(days)
        for cycle in range(1, cycles + 1)
    )


def test_history_split_is_chronological_and_counts_interday_reviews() -> None:
    split = split_history(make_history())
    assert split.train_examples == 600
    assert len(split.validation) == 200
    assert max(x.reviewed_at for x in split.train) < min(
        x.reviewed_at for x in split.validation
    )
    loss, count = validation_loss(split, DEFAULT_PARAMETERS, StudyConfig())
    assert loss is not None and loss > 0
    assert count == 200


def test_only_first_64_reviews_per_cycle_count_for_training() -> None:
    split = split_history(make_history(cycles=1, days=100))
    assert len(split.train) == 80
    assert split.train_examples == 63


def test_optimizer_prefix_is_deterministic_at_timestamp_ties() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    reviews = (
        tuple(
            OptimizationReview(1, 3, start + timedelta(days=day), day)
            for day in range(63)
        )
        + (
            OptimizationReview(1, 1, start + timedelta(days=63), 640),
            OptimizationReview(1, 4, start + timedelta(days=63), 641),
            OptimizationReview(1, 3, start + timedelta(days=64), 642),
        )
        + make_history(cycles=2, days=70)[1::2]
    )
    selected = optimizer_training_reviews(tuple(reversed(reviews)))
    assert Counter(review.cycle_id for review in selected) == {1: 64, 2: 64}
    assert [review.review_id for review in selected if review.cycle_id == 1] == [
        *range(63),
        640,
    ]
    assert selected == tuple(
        sorted(selected, key=lambda review: (review.reviewed_at, review.review_id))
    )


def test_split_keeps_timestamp_group_at_holdout_boundary() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    reviews = tuple(
        OptimizationReview(1, 3, start + timedelta(days=min(day, 79)), day)
        for day in range(81)
    ) + tuple(
        OptimizationReview(1, 3, start + timedelta(days=day), day)
        for day in range(81, 100)
    )
    split = split_history(tuple(reversed(reviews)))
    assert [review.review_id for review in split.train] == list(range(79))
    assert [review.review_id for review in split.validation] == list(range(79, 100))
    assert split.train_examples == 63


async def test_worker_payload_limits_each_cycle_without_trimming_replay(
    monkeypatch,
) -> None:
    split = split_history(make_history(cycles=2, days=100))
    process = AsyncMock()
    process.returncode = 0
    process.communicate.return_value = (
        json.dumps(list(DEFAULT_PARAMETERS)).encode(),
        b"",
    )
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr("asyncio.create_subprocess_exec", spawn)
    parameters = await FsrsOptimizer().optimize(
        tuple(reversed(split.train)), StudyConfig()
    )
    assert parameters == list(DEFAULT_PARAMETERS)
    payload = json.loads(process.communicate.await_args.args[0])
    assert Counter(review["cycle_id"] for review in payload["reviews"]) == {
        1: 64,
        2: 64,
    }
    assert payload["reviews"] == [
        {
            "cycle_id": review.cycle_id,
            "rating": review.rating,
            "reviewed_at": review.reviewed_at.isoformat(),
        }
        for review in split.train[:128]
    ]
    assert len(split.train) == 160 and len(split.validation) == 40
    spawn.assert_awaited_once()


def test_capped_input_preserves_fsrs_632_optimizer_parameters(monkeypatch) -> None:
    pytest.importorskip("torch")
    pytest.importorskip("pandas")
    pytest.importorskip("tqdm")
    import fsrs.optimizer as optimizer_module
    from fsrs import ReviewLog

    assert version("fsrs") == "6.3.2"
    config = StudyConfig()
    monkeypatch.setattr(
        optimizer_module,
        "Scheduler",
        partial(
            Scheduler,
            learning_steps=(timedelta(seconds=config.learning_step_seconds),),
            relearning_steps=(timedelta(seconds=config.relearning_step_seconds),),
            enable_fuzzing=False,
        ),
    )

    train = split_history(make_history(cycles=9, days=100)).train
    boundary = next(review for review in train if review.review_id == 64 * 9 + 1)
    train = tuple(
        OptimizationReview(
            review.cycle_id,
            review.rating,
            boundary.reviewed_at - timedelta(days=1)
            if review.review_id == boundary.review_id
            else review.reviewed_at,
            review.review_id,
        )
        for review in train
    )

    def optimize(reviews):
        logs = [
            ReviewLog(
                card_id=review.cycle_id,
                rating=Rating(review.rating),
                review_datetime=review.reviewed_at,
                review_duration=None,
            )
            for review in reviews
        ]
        return optimizer_module.Optimizer(logs).compute_optimal_parameters()

    assert optimize(train) == optimize(optimizer_training_reviews(train))


def reference_validation_loss(split: HistorySplit, config: StudyConfig):
    """Unfiltered replay, intentionally independent of the optimized traversal."""
    scheduler = Scheduler(
        parameters=DEFAULT_PARAMETERS,
        desired_retention=config.desired_retention,
        learning_steps=(timedelta(seconds=config.learning_step_seconds),),
        relearning_steps=(timedelta(seconds=config.relearning_step_seconds),),
        maximum_interval=config.maximum_interval,
        enable_fuzzing=False,
    )
    cards = {}
    losses = []
    for history, held_out in ((split.train, False), (split.validation, True)):
        for review in history:
            when = review.reviewed_at.astimezone(UTC)
            card = cards.get(review.cycle_id, Card(card_id=review.cycle_id, due=when))
            if held_out and card.last_review and (when - card.last_review).days > 0:
                probability = scheduler.get_card_retrievability(card, when)
                probability = min(1 - 1e-15, max(1e-15, probability))
                losses.append(
                    -math.log1p(-probability)
                    if review.rating == 1
                    else -math.log(probability)
                )
            cards[review.cycle_id], _ = scheduler.review_card(
                card, Rating(review.rating), review_datetime=when
            )
    return (sum(losses) / len(losses) if losses else None), len(losses)


@pytest.mark.parametrize("has_validation", [False, True])
def test_validation_replays_only_held_out_cycles_with_complete_train_history(
    monkeypatch, has_validation
) -> None:
    from application.study.optimization import quality

    split = split_history(make_history(cycles=2, days=100))
    validation = tuple(review for review in split.validation if review.cycle_id == 1)
    split = HistorySplit(split.train, validation if has_validation else (), 126)
    config = StudyConfig()
    expected = reference_validation_loss(split, config)
    real_scheduler = Scheduler
    schedulers = []

    def track_scheduler(**kwargs):
        scheduler = MagicMock(wraps=real_scheduler(**kwargs))
        schedulers.append(scheduler)
        return scheduler

    monkeypatch.setattr(quality, "Scheduler", track_scheduler)
    actual = validation_loss(split, DEFAULT_PARAMETERS, config)
    assert actual == expected
    assert actual[1] == (20 if has_validation else 0)
    replayed = schedulers[0].review_card.call_args_list
    expected_reviews = (
        [review for review in (*split.train, *split.validation) if review.cycle_id == 1]
        if has_validation
        else []
    )
    assert len(expected_reviews) == (100 if has_validation else 0)
    assert [
        (call.args[0].card_id, call.kwargs["review_datetime"]) for call in replayed
    ] == [(review.cycle_id, review.reviewed_at) for review in expected_reviews]
    assert schedulers[0].get_card_retrievability.call_count == actual[1]


def test_same_timestamp_is_never_split_between_training_and_validation() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    reviews = tuple(OptimizationReview(i, 3, timestamp, i) for i in range(1, 20))
    split = split_history(reviews)
    assert split.train == ()
    assert len(split.validation) == 19


@pytest.mark.parametrize(
    "values", [[0.0], [float("nan")] * 21, [True] * 21, [10000.0] * 21]
)
def test_validate_parameters_rejects_invalid_weights(values) -> None:
    with pytest.raises(ValueError):
        validate_parameters(values)


class FakeRepository:
    def __init__(
        self, history: OptimizationHistory | None, *, locked: bool = True
    ) -> None:
        self.data = history
        self.locked = locked
        self.publish = AsyncMock(return_value=True)
        self.history = AsyncMock(return_value=history)

    @asynccontextmanager
    async def user_lock(self, user_id):
        yield object() if self.locked else None


async def test_insufficient_history_does_not_train_or_publish() -> None:
    repo = FakeRepository(OptimizationHistory(None, make_history(cycles=10)))
    optimizer = AsyncMock()
    result = await FsrsOptimizationService(
        repo, optimizer, StudyConfig()
    ).optimize_user(7)
    assert result.status == "insufficient_data"
    optimizer.optimize.assert_not_awaited()
    repo.publish.assert_not_awaited()


async def test_already_running_does_not_load_history() -> None:
    repo = FakeRepository(None, locked=False)
    result = await FsrsOptimizationService(
        repo, AsyncMock(), StudyConfig()
    ).optimize_user(7)
    assert result.status == "already_running"
    repo.history.assert_not_awaited()


async def test_no_improvement_does_not_replace_existing_weights() -> None:
    weights = tuple(DEFAULT_PARAMETERS)
    repo = FakeRepository(OptimizationHistory(weights, make_history()))
    optimizer = AsyncMock()
    optimizer.optimize.return_value = list(weights)
    result = await FsrsOptimizationService(
        repo, optimizer, StudyConfig()
    ).optimize_user(7)
    assert result.status == "not_improved"
    assert result.train_reviews == 600 and result.validation_reviews == 200
    assert result.current_loss == result.candidate_loss
    repo.publish.assert_not_awaited()


async def test_insufficient_validation_does_not_train() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    reviews = tuple(
        OptimizationReview(cycle, 3, start + timedelta(days=day), day * 200 + cycle)
        for day in range(4)
        for cycle in range(1, 201)
    ) + tuple(
        OptimizationReview(cycle, 3, start + timedelta(days=3, hours=1), 800 + cycle)
        for cycle in range(1, 201)
    )
    repo = FakeRepository(OptimizationHistory(None, reviews))
    optimizer = AsyncMock()
    result = await FsrsOptimizationService(
        repo, optimizer, StudyConfig()
    ).optimize_user(7)
    assert result.status == "insufficient_data"
    assert result.train_reviews == 600 and result.validation_reviews == 0
    optimizer.optimize.assert_not_awaited()
    repo.publish.assert_not_awaited()


async def test_improvement_publishes_only_with_original_parameters(monkeypatch) -> None:
    from application.study.optimization import service as service_module

    repo = FakeRepository(OptimizationHistory(None, make_history()))
    optimizer = AsyncMock()
    candidate = list(DEFAULT_PARAMETERS)
    candidate[0] *= 1.1
    optimizer.optimize.return_value = candidate
    monkeypatch.setattr(
        service_module,
        "validation_loss",
        lambda split, weights, config: (
            0.7 if tuple(weights) == tuple(DEFAULT_PARAMETERS) else 0.6,
            200,
        ),
    )
    result = await FsrsOptimizationService(
        repo, optimizer, StudyConfig()
    ).optimize_user(7)
    assert result.status == "updated"
    assert repo.publish.await_args.kwargs["previous"] is None
    assert repo.publish.await_args.kwargs["parameters"] == tuple(candidate)
    train = optimizer.optimize.await_args.args[0]
    assert len(train) == 800


async def test_stale_weights_are_not_overwritten(monkeypatch) -> None:
    from application.study.optimization import service as service_module

    repo = FakeRepository(OptimizationHistory(None, make_history()))
    repo.publish.return_value = False
    optimizer = AsyncMock()
    optimizer.optimize.return_value = list(DEFAULT_PARAMETERS)
    losses = iter([(0.7, 200), (0.6, 200)])
    monkeypatch.setattr(service_module, "validation_loss", lambda *args: next(losses))
    result = await FsrsOptimizationService(
        repo, optimizer, StudyConfig()
    ).optimize_user(7)
    assert result.status == "failed"
    assert "changed" in result.message


async def test_invalid_candidate_is_not_published(monkeypatch) -> None:
    from application.study.optimization import service as service_module

    repo = FakeRepository(OptimizationHistory(None, make_history()))
    optimizer = AsyncMock()
    optimizer.optimize.return_value = [float("nan")] * 21
    monkeypatch.setattr(service_module, "validation_loss", lambda *args: (0.7, 200))
    result = await FsrsOptimizationService(
        repo, optimizer, StudyConfig()
    ).optimize_user(7)
    assert result.status == "failed"
    repo.publish.assert_not_awaited()
