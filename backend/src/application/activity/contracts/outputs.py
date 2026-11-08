from dataclasses import dataclass
from datetime import date

from application.shared.contracts.base import ReadSchema
from application.shared.contracts.types import BigIntId, NonNegativeInt32


@dataclass(frozen=True)
class StreakResult:
    streak_days: int
    max_streak_days: int
    last_streak_date: date | None


class UserDailyActivityOutput(ReadSchema):
    id: BigIntId
    user_id: BigIntId
    activity_date: date
    cards_reviewed: NonNegativeInt32
    completed: bool
