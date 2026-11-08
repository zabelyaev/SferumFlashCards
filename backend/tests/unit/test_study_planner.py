from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from application.study.contracts.outputs import StudyLimitsOutput
from application.study.contracts.types import DailyUsage
from application.study.database.models import StudySessionCard
from application.study.database.types import CandidateMetadata
from application.study.services.planner import StudyPlanner
from common.config.study import StudyConfig


def test_one_step_fsrs_and_short_term_learning() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    planner = StudyPlanner(StudyConfig())
    config = planner.config_snapshot()
    state = planner.new_card(42, now)
    again = planner.review(state, 1, now, config)
    assert again.due_date == now + timedelta(minutes=1)
    assert not again.completed
    hard = planner.review(state, 2, now, config)
    assert hard.due_date == now + timedelta(seconds=90)
    assert not hard.completed
    good = planner.review(state, 3, now, config)
    assert good.completed
    assert good.due_date >= now + timedelta(days=1)


def test_queue_prefers_due_learning_and_uses_learn_ahead() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    planner = StudyPlanner(StudyConfig())
    config = planner.config_snapshot()
    initial = planner.new_card(1, now)
    learning = planner.review(initial, 1, now, config).fsrs_state
    retry = StudySessionCard(
        card_id=1, order_index=0, attempts_count=1, fsrs_state=learning
    )
    fresh = StudySessionCard(
        card_id=2, order_index=1, attempts_count=0, fsrs_state=planner.new_card(2, now)
    )
    assert planner.next_card([retry, fresh], now, config) is fresh
    assert planner.next_card([retry], now, config) is retry
    assert (
        planner.next_card([retry, fresh], now + timedelta(minutes=2), config) is retry
    )


def test_queue_rejects_incomplete_steps_outside_the_ahead_window() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    planner = StudyPlanner(StudyConfig())
    state = planner.new_card(1, now)
    state["due"] = (now + timedelta(hours=1)).isoformat()
    item = StudySessionCard(
        card_id=1, order_index=0, attempts_count=1, fsrs_state=state
    )
    assert planner.next_card([], now, planner.config_snapshot()) is None
    with pytest.raises(ValueError, match="learn-ahead"):
        planner.next_card([item], now, planner.config_snapshot())


def test_invalid_learn_ahead_configuration_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StudyConfig(learn_ahead_seconds=899)
    assert StudyConfig(learn_ahead_seconds=900).learn_ahead_seconds == 900


def test_day_end_respects_dst_and_sliding_expiration() -> None:
    now = datetime(2026, 3, 29, 10, tzinfo=UTC)
    planner = StudyPlanner(StudyConfig())
    day = planner.study_day(now, "Europe/Berlin")
    assert day.study_date.isoformat() == "2026-03-29"
    assert day.ends_at == datetime(2026, 3, 29, 22, tzinfo=UTC)
    assert planner.expiration(
        day.ends_at, day.ends_at - timedelta(minutes=1)
    ) == day.ends_at + timedelta(minutes=29)


def test_review_uses_saved_session_config() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    original = StudyPlanner(StudyConfig(enable_fuzzing=False, learning_step_seconds=60))
    changed = StudyPlanner(StudyConfig(enable_fuzzing=False, learning_step_seconds=120))
    snapshot = original.config_snapshot()
    state = original.new_card(42, now)
    saved_result = changed.review(state, 1, now, snapshot)
    assert saved_result == original.review(state, 1, now, snapshot)
    assert saved_result.due_date == now + timedelta(seconds=60)
    new_result = changed.review(state, 1, now, changed.config_snapshot())
    assert new_result.due_date == now + timedelta(seconds=120)


def test_select_cards_keeps_used_cards_and_reserves_remaining_capacity() -> None:
    planner = StudyPlanner(StudyConfig())
    limits = StudyLimitsOutput(daily_total_cards_limit=20, daily_new_cards_limit=2)
    usage = DailyUsage(card_ids=frozenset(range(1, 21)), new_card_ids=frozenset({1}))
    now = datetime(2026, 1, 1, tzinfo=UTC)
    candidates = [
        CandidateMetadata(21, 0, now),
        CandidateMetadata(1, 1, None),
        CandidateMetadata(2, 2, now),
        CandidateMetadata(22, 3, None),
    ]
    selected = planner.select_cards(candidates, usage=usage, limits=limits)
    assert [card.card_id for card in selected] == [1, 2]
    quota = planner.quota(usage, limits)
    assert (
        quota.total_used,
        quota.new_used,
        quota.total_remaining,
        quota.new_remaining,
    ) == (20, 1, 0, 0)
    assert usage.card_ids == frozenset(range(1, 21))
    assert usage.new_card_ids == frozenset({1})


def test_select_cards_skips_new_limit_but_allows_due_and_previous_new() -> None:
    planner = StudyPlanner(StudyConfig())
    limits = StudyLimitsOutput(daily_total_cards_limit=20, daily_new_cards_limit=1)
    usage = DailyUsage(card_ids=frozenset({1}), new_card_ids=frozenset({1}))
    now = datetime(2026, 1, 1, tzinfo=UTC)
    candidates = [
        CandidateMetadata(2, 0, None),
        CandidateMetadata(3, 1, now),
        CandidateMetadata(1, 2, None),
    ]
    selected = planner.select_cards(candidates, usage=usage, limits=limits)
    assert [card.card_id for card in selected] == [3, 1]
    quota = planner.quota(usage, limits)
    assert quota.total_remaining == 19
    assert quota.new_remaining == 0


@pytest.mark.parametrize(
    ("has_cards", "has_candidates", "reason"),
    [
        (False, False, "empty_deck"),
        (True, True, "limits_reached"),
        (True, False, "nothing_due"),
    ],
)
def test_no_work_reason(has_cards, has_candidates, reason) -> None:
    planner = StudyPlanner(StudyConfig())
    assert (
        planner.no_work_reason(has_cards=has_cards, has_candidates=has_candidates)
        == reason
    )
