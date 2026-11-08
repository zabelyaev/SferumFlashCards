from typing import TYPE_CHECKING

from fastapi import status

from api.v1.flashcards.cards.contracts.mappers import to_card_response
from api.v1.study.contracts.responses import (
    ActiveSessionsResponse,
    DailyQuotaResponse,
    LimitsResponse,
    NoWorkResponse,
    ProgressResponse,
    ReviewResponse,
    SessionStateResponse,
    SessionViewResponse,
    StreakStateResponse,
)
from application.study.contracts.inputs import (
    ReviewCreateInput,
    StudySessionCreateInput,
)
from application.study.contracts.outputs import StudySessionOpenedOutput

if TYPE_CHECKING:
    from api.v1.study.contracts.requests import OpenSessionRequest, ReviewRequest
    from application.study.contracts.outputs import (
        ActiveStudySessionsOutput,
        DailyQuotaOutput,
        ReviewResultOutput,
        StudyLimitsOutput,
        StudyOpenResult,
        StudyProgressOutput,
        StudySessionOutput,
        StudySessionViewOutput,
        StudyStreakOutput,
    )


def to_session_create_input(model: OpenSessionRequest) -> StudySessionCreateInput:
    return StudySessionCreateInput(deck_id=model.deck_id)


def to_review_create_input(model: ReviewRequest) -> ReviewCreateInput:
    return ReviewCreateInput(
        card_id=model.card_id, rating=model.rating, answer_token=model.answer_token
    )


def to_limits_response(model: StudyLimitsOutput) -> LimitsResponse:
    return LimitsResponse(
        daily_total_cards_limit=model.daily_total_cards_limit,
        daily_new_cards_limit=model.daily_new_cards_limit,
    )


def to_progress_response(model: StudyProgressOutput) -> ProgressResponse:
    return ProgressResponse(
        total_cards=model.total_cards,
        completed_cards=model.completed_cards,
        remaining_cards=model.remaining_cards,
    )


def to_session_state_response(model: StudySessionOutput) -> SessionStateResponse:
    return SessionStateResponse(
        id=model.id,
        deck_id=model.deck_id,
        study_date=model.study_date,
        status=model.status,
        started_at=model.started_at,
        last_activity_at=model.last_activity_at,
        expires_at=model.expires_at,
        finished_at=model.finished_at,
        finish_reason=model.finish_reason,
        limits=to_limits_response(model.limits),
        progress=to_progress_response(model.progress),
    )


def to_quota_response(model: DailyQuotaOutput) -> DailyQuotaResponse:
    return DailyQuotaResponse(
        total_used=model.total_used,
        new_used=model.new_used,
        total_remaining=model.total_remaining,
        new_remaining=model.new_remaining,
    )


def to_streak_response(model: StudyStreakOutput) -> StreakStateResponse:
    return StreakStateResponse(
        streak_days=model.streak_days,
        max_streak_days=model.max_streak_days,
        last_streak_date=model.last_streak_date,
    )


def to_review_response(model: ReviewResultOutput) -> ReviewResponse:
    return ReviewResponse(
        session=to_session_state_response(model.session),
        current_card_id=model.current_card_id,
        answer_token=model.answer_token,
        quota=to_quota_response(model.quota),
        streak=to_streak_response(model.streak),
    )


def to_session_view_response(model: StudySessionViewOutput) -> SessionViewResponse:
    return SessionViewResponse(
        session=to_session_state_response(model.session),
        current_card_id=model.current_card_id,
        answer_token=model.answer_token,
        quota=to_quota_response(model.quota),
        streak=to_streak_response(model.streak),
        cards=[to_card_response(card) for card in model.cards],
    )


def to_open_session_response(
    model: StudyOpenResult,
) -> tuple[SessionViewResponse | NoWorkResponse, int]:
    if isinstance(model, StudySessionOpenedOutput):
        code = status.HTTP_201_CREATED if model.created else status.HTTP_200_OK
        return to_session_view_response(model.view), code

    return NoWorkResponse(
        session=None,
        deck_id=model.deck_id,
        study_date=model.study_date,
        cards=[],
        current_card_id=None,
        answer_token=None,
        limits=to_limits_response(model.limits),
        quota=to_quota_response(model.quota),
        streak=to_streak_response(model.streak),
        reason=model.reason,
    ), status.HTTP_200_OK


def to_active_sessions_response(
    model: ActiveStudySessionsOutput,
) -> ActiveSessionsResponse:
    return ActiveSessionsResponse(
        items=[to_session_state_response(session) for session in model.items],
        total=model.total,
    )
