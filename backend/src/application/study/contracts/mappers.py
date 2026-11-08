from typing import TYPE_CHECKING, cast

from application.flashcards.cards.contracts.outputs import CardOutput
from application.study.contracts.outputs import (
    ActiveStudySessionsOutput,
    ReviewResultOutput,
    StudyLimitsOutput,
    StudyNoWorkOutput,
    StudyProgressOutput,
    StudySessionOutput,
    StudySessionViewOutput,
    StudyStreakOutput,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date
    from typing import Literal

    from application.accounts.users.database.models import User
    from application.study.contracts.outputs import DailyQuotaOutput
    from application.study.contracts.types import JsonObject, NoWorkReason
    from application.study.database.models import StudySession, StudySessionCard


def to_study_limits_output(source: User | StudySession) -> StudyLimitsOutput:
    return StudyLimitsOutput(
        daily_total_cards_limit=source.daily_total_cards_limit,
        daily_new_cards_limit=source.daily_new_cards_limit,
    )


def to_study_session_output(session: StudySession) -> StudySessionOutput:
    return StudySessionOutput(
        id=session.id,
        deck_id=session.deck_id,
        study_date=session.study_date,
        status=cast("Literal['active', 'completed', 'abandoned']", session.status),
        started_at=session.started_at,
        last_activity_at=session.last_activity_at,
        expires_at=session.expires_at,
        finished_at=session.finished_at,
        finish_reason=cast("Literal['timeout'] | None", session.finish_reason),
        limits=to_study_limits_output(session),
        progress=StudyProgressOutput(
            total_cards=session.total_cards,
            completed_cards=session.completed_cards,
            remaining_cards=session.total_cards - session.completed_cards,
        ),
    )


def to_study_streak_output(user: User) -> StudyStreakOutput:
    return StudyStreakOutput(
        streak_days=user.streak_days,
        max_streak_days=user.max_streak_days,
        last_streak_date=user.last_streak_date,
    )


def card_output_from_snapshot(snapshot: JsonObject) -> CardOutput:
    return CardOutput.model_validate(snapshot)


def review_result_from_json(data: JsonObject) -> ReviewResultOutput:
    return ReviewResultOutput.model_validate(data)


def to_review_result_output(
    session: StudySession, *, user: User, quota: DailyQuotaOutput
) -> ReviewResultOutput:
    return ReviewResultOutput(
        session=to_study_session_output(session),
        current_card_id=session.current_card_id,
        answer_token=session.answer_token,
        quota=quota,
        streak=to_study_streak_output(user),
    )


def to_session_view_output(
    session: StudySession,
    *,
    user: User,
    quota: DailyQuotaOutput,
    cards: Sequence[StudySessionCard],
) -> StudySessionViewOutput:
    return StudySessionViewOutput(
        session=to_study_session_output(session),
        current_card_id=session.current_card_id,
        answer_token=session.answer_token,
        quota=quota,
        streak=to_study_streak_output(user),
        cards=[card_output_from_snapshot(card.snapshot) for card in cards],
    )


def to_no_work_output(
    *,
    deck_id: int,
    study_date: date,
    user: User,
    limits: StudyLimitsOutput,
    quota: DailyQuotaOutput,
    reason: NoWorkReason,
) -> StudyNoWorkOutput:
    return StudyNoWorkOutput(
        deck_id=deck_id,
        study_date=study_date,
        limits=limits,
        quota=quota,
        streak=to_study_streak_output(user),
        reason=reason,
    )


def to_active_sessions_output(
    sessions: Sequence[StudySession],
) -> ActiveStudySessionsOutput:
    return ActiveStudySessionsOutput(
        items=[to_study_session_output(session) for session in sessions],
        total=len(sessions),
    )
