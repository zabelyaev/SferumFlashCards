from datetime import date

from pydantic import AwareDatetime, Field, HttpUrl, JsonValue

from application.shared.contracts.base import ReadSchema
from application.shared.contracts.types import (
    BigIntId,
    DailyNewCardsLimit,
    DailyTotalCardsLimit,
    NonNegativeInt32,
    TimezoneName,
)
from application.shared.enums import UserRole


class CurrentUserOutput(ReadSchema):
    id: BigIntId
    is_active: bool


class UserProfileOutput(ReadSchema):
    id: BigIntId
    vk_user_id: BigIntId
    first_name: str
    last_name: str
    avatar_url: HttpUrl | None
    role: UserRole
    is_active: bool
    timezone: TimezoneName
    streak_days: NonNegativeInt32
    max_streak_days: NonNegativeInt32
    last_streak_date: date | None
    daily_total_cards_limit: DailyTotalCardsLimit
    daily_new_cards_limit: DailyNewCardsLimit
    settings: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: AwareDatetime
    updated_at: AwareDatetime
