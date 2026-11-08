from datetime import date
from typing import Literal

from pydantic import AwareDatetime

from application.flashcards.cards.contracts.outputs import CardOutput
from application.shared.contracts.base import ReadSchema
from application.shared.contracts.types import (
    BigIntId,
    DailyNewCardsLimit,
    DailyTotalCardsLimit,
    NonNegativeInt32,
    Rating,
)
from common.schemas.base import BaseSchema


class StudyLimitsOutput(BaseSchema):
    daily_total_cards_limit: DailyTotalCardsLimit
    daily_new_cards_limit: DailyNewCardsLimit


class StudyProgressOutput(BaseSchema):
    total_cards: NonNegativeInt32
    completed_cards: NonNegativeInt32
    remaining_cards: NonNegativeInt32


class StudySessionOutput(BaseSchema):
    id: BigIntId
    deck_id: BigIntId | None
    study_date: date
    status: Literal["active", "completed", "abandoned"]
    started_at: AwareDatetime
    last_activity_at: AwareDatetime
    expires_at: AwareDatetime
    finished_at: AwareDatetime | None
    finish_reason: Literal["timeout"] | None
    limits: StudyLimitsOutput
    progress: StudyProgressOutput


class DailyQuotaOutput(BaseSchema):
    total_used: NonNegativeInt32
    new_used: NonNegativeInt32
    total_remaining: NonNegativeInt32
    new_remaining: NonNegativeInt32


class StudyStreakOutput(BaseSchema):
    streak_days: NonNegativeInt32
    max_streak_days: NonNegativeInt32
    last_streak_date: date | None


class ReviewResultOutput(BaseSchema):
    session: StudySessionOutput
    current_card_id: BigIntId | None
    answer_token: str | None
    quota: DailyQuotaOutput
    streak: StudyStreakOutput


class StudySessionViewOutput(ReviewResultOutput):
    cards: list[CardOutput]


class StudySessionOpenedOutput(BaseSchema):
    view: StudySessionViewOutput
    created: bool


class StudyNoWorkOutput(BaseSchema):
    deck_id: BigIntId
    study_date: date
    limits: StudyLimitsOutput
    quota: DailyQuotaOutput
    streak: StudyStreakOutput
    reason: Literal["empty_deck", "limits_reached", "nothing_due"]


type StudyOpenResult = StudySessionOpenedOutput | StudyNoWorkOutput


class ActiveStudySessionsOutput(BaseSchema):
    items: list[StudySessionOutput]
    total: NonNegativeInt32


class CardReviewOutput(ReadSchema):
    id: BigIntId
    user_id: BigIntId
    card_id: BigIntId
    deck_id: BigIntId
    cycle_id: BigIntId
    fsrs_state: dict
    due_date: AwareDatetime
    last_reviewed: AwareDatetime


class StudySessionCardOutput(ReadSchema):
    id: BigIntId
    session_id: BigIntId
    card_id: BigIntId
    source_card_id: BigIntId | None
    snapshot: CardOutput
    order_index: NonNegativeInt32
    fsrs_state: dict
    cycle_id: BigIntId | None
    was_new: bool
    attempts_count: NonNegativeInt32
    completed_at: AwareDatetime | None


class ReviewLogOutput(ReadSchema):
    id: BigIntId
    user_id: BigIntId
    card_id: BigIntId
    deck_id: BigIntId
    session_id: BigIntId
    cycle_id: BigIntId | None
    study_date: date
    answer_token: str
    rating: Rating
    was_new: bool
    result: ReviewResultOutput
    reviewed_at: AwareDatetime
