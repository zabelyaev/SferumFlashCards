from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from importlib.metadata import version
from typing import TYPE_CHECKING, cast
from zoneinfo import ZoneInfo

from fsrs import Card, Rating, Scheduler, State

from application.study.contracts.outputs import DailyQuotaOutput
from application.study.contracts.types import ReviewCalculation, StudyDay

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fsrs.card import CardDict
    from fsrs.scheduler import SchedulerDict

    from application.study.contracts.outputs import StudyLimitsOutput
    from application.study.contracts.types import (
        DailyUsage,
        DailyUsageCounts,
        FsrsState,
        NoWorkReason,
        SchedulerSnapshot,
    )
    from application.study.database.models import StudySessionCard
    from application.study.database.types import CandidateMetadata
    from common.config.study import StudyConfig


class StudyPlanner:
    def __init__(self, config: StudyConfig) -> None:
        self._config = config

    def study_day(self, now: datetime, timezone: str) -> StudyDay:
        zone = ZoneInfo(timezone)
        day = now.astimezone(zone).date()
        tomorrow = day + timedelta(days=1)
        end = datetime.combine(tomorrow, time.min, tzinfo=zone).astimezone(UTC)
        return StudyDay(study_date=day, ends_at=end)

    def expiration(self, day_end: datetime, activity_at: datetime) -> datetime:
        return max(day_end, activity_at + timedelta(minutes=30))

    def quota(
        self, usage: DailyUsage | DailyUsageCounts, limits: StudyLimitsOutput
    ) -> DailyQuotaOutput:
        remaining = max(0, limits.daily_total_cards_limit - usage.total_used)
        return DailyQuotaOutput(
            total_used=usage.total_used,
            new_used=usage.new_used,
            total_remaining=remaining,
            new_remaining=min(
                remaining,
                max(0, limits.daily_new_cards_limit - usage.new_used),
            ),
        )

    def no_work_reason(self, *, has_cards: bool, has_candidates: bool) -> NoWorkReason:
        if not has_cards:
            return "empty_deck"
        return "limits_reached" if has_candidates else "nothing_due"

    def select_cards(
        self,
        candidates: Sequence[CandidateMetadata],
        *,
        usage: DailyUsage,
        limits: StudyLimitsOutput,
    ) -> list[CandidateMetadata]:
        chosen: list[CandidateMetadata] = []
        total_reserved, new_reserved = len(usage.card_ids), len(usage.new_card_ids)
        for candidate in candidates:
            total_cost = int(candidate.card_id not in usage.card_ids)
            new_cost = int(
                candidate.is_new and candidate.card_id not in usage.new_card_ids
            )
            if (total_cost and total_reserved >= limits.daily_total_cards_limit) or (
                new_cost and new_reserved >= limits.daily_new_cards_limit
            ):
                continue
            chosen.append(candidate)
            total_reserved += total_cost
            new_reserved += new_cost
        return chosen

    def config_snapshot(
        self, parameters: Sequence[float] | None = None
    ) -> SchedulerSnapshot:
        config = self._config
        kwargs = {"parameters": parameters} if parameters is not None else {}
        scheduler = Scheduler(
            desired_retention=config.desired_retention,
            learning_steps=(timedelta(seconds=config.learning_step_seconds),),
            relearning_steps=(timedelta(seconds=config.relearning_step_seconds),),
            maximum_interval=config.maximum_interval,
            enable_fuzzing=config.enable_fuzzing,
            **kwargs,
        )
        return cast(
            "SchedulerSnapshot",
            {
                "library_version": version("fsrs"),
                "scheduler": scheduler.to_dict(),
                "learn_ahead_seconds": config.learn_ahead_seconds,
            },
        )

    def new_card(self, card_id: int, now: datetime) -> FsrsState:
        return cast("FsrsState", dict(Card(card_id=card_id, due=now).to_dict()))

    def review(
        self, state: FsrsState, rating: int, now: datetime, config: SchedulerSnapshot
    ) -> ReviewCalculation:
        scheduler = Scheduler.from_dict(cast("SchedulerDict", config["scheduler"]))
        card, _ = scheduler.review_card(
            Card.from_dict(cast("CardDict", state)), Rating(rating), review_datetime=now
        )
        return ReviewCalculation(
            fsrs_state=cast("FsrsState", dict(card.to_dict())),
            due_date=card.due,
            completed=card.state == State.Review,
        )

    def next_card(
        self,
        cards: Sequence[StudySessionCard],
        now: datetime,
        config: SchedulerSnapshot,
    ) -> StudySessionCard | None:
        ahead_seconds = cast(int, config["learn_ahead_seconds"])
        remaining = [card for card in cards if card.completed_at is None]
        if not remaining:
            return None
        ready = [
            card
            for card in remaining
            if card.attempts_count == 0
            or datetime.fromisoformat(card.fsrs_state["due"]) <= now
        ]
        if ready:
            return min(ready, key=self._priority)
        early = [
            card
            for card in remaining
            if datetime.fromisoformat(card.fsrs_state["due"])
            <= now + timedelta(seconds=ahead_seconds)
        ]
        if early:
            return min(
                early, key=lambda card: (card.fsrs_state["due"], card.order_index)
            )
        raise ValueError("No card is available within the learn-ahead window")

    @staticmethod
    def _priority(card: StudySessionCard) -> tuple[int, int]:
        state = card.fsrs_state
        if state.get("last_review") is not None and state.get("state") in (1, 3):
            return (0, card.order_index)
        if state.get("last_review") is not None:
            return (1, card.order_index)
        return (2, card.order_index)
