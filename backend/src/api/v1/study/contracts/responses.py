from datetime import date
from typing import Literal

from pydantic import AwareDatetime

from api.types import (
    BigIntId,
    DailyNewCardsLimit,
    DailyTotalCardsLimit,
    NonNegativeInt32,
)
from api.v1.flashcards.cards.contracts.responses import CardResponse
from common.schemas.base import BaseSchema


class LimitsResponse(BaseSchema):
    daily_total_cards_limit: DailyTotalCardsLimit
    daily_new_cards_limit: DailyNewCardsLimit


class ProgressResponse(BaseSchema):
    total_cards: NonNegativeInt32
    completed_cards: NonNegativeInt32
    remaining_cards: NonNegativeInt32


class SessionStateResponse(BaseSchema):
    id: BigIntId
    deck_id: BigIntId | None
    study_date: date
    status: Literal["active", "completed", "abandoned"]
    started_at: AwareDatetime
    last_activity_at: AwareDatetime
    expires_at: AwareDatetime
    finished_at: AwareDatetime | None
    finish_reason: Literal["timeout"] | None
    limits: LimitsResponse
    progress: ProgressResponse


class DailyQuotaResponse(BaseSchema):
    total_used: NonNegativeInt32
    new_used: NonNegativeInt32
    total_remaining: NonNegativeInt32
    new_remaining: NonNegativeInt32


class StreakStateResponse(BaseSchema):
    streak_days: NonNegativeInt32
    max_streak_days: NonNegativeInt32
    last_streak_date: date | None


class ReviewResponse(BaseSchema):
    session: SessionStateResponse
    current_card_id: BigIntId | None
    answer_token: str | None
    quota: DailyQuotaResponse
    streak: StreakStateResponse


class SessionViewResponse(ReviewResponse):
    cards: list[CardResponse]


class NoWorkResponse(BaseSchema):
    session: None
    deck_id: BigIntId
    study_date: date
    cards: list[CardResponse]
    current_card_id: None
    answer_token: None
    limits: LimitsResponse
    quota: DailyQuotaResponse
    streak: StreakStateResponse
    reason: Literal["empty_deck", "limits_reached", "nothing_due"]


class ActiveSessionsResponse(BaseSchema):
    items: list[SessionStateResponse]
    total: NonNegativeInt32
