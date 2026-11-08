from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import date, datetime

    from pydantic import JsonValue

type JsonObject = dict[str, JsonValue]
type FsrsState = JsonObject
type SchedulerSnapshot = JsonObject
type NoWorkReason = Literal["empty_deck", "limits_reached", "nothing_due"]


@dataclass(frozen=True)
class StudyDay:
    study_date: date
    ends_at: datetime


@dataclass(frozen=True)
class DailyUsage:
    card_ids: frozenset[int]
    new_card_ids: frozenset[int]

    @property
    def total_used(self) -> int:
        return len(self.card_ids)

    @property
    def new_used(self) -> int:
        return len(self.new_card_ids)


@dataclass(frozen=True)
class DailyUsageCounts:
    total_used: int
    new_used: int


@dataclass(frozen=True)
class ReviewCalculation:
    fsrs_state: FsrsState
    due_date: datetime
    completed: bool
