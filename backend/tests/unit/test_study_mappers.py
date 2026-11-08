import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.dependencies.services import get_study_service, get_user_service
from api.v1.study.contracts.mappers import (
    to_active_sessions_response,
    to_open_session_response,
    to_review_create_input,
    to_review_response,
    to_session_create_input,
    to_session_view_response,
)
from api.v1.study.contracts.requests import OpenSessionRequest, ReviewRequest
from application.accounts.users.service import UserService
from application.flashcards.cards.contracts.outputs import CardOutput
from application.study.contracts.inputs import (
    ReviewCreateInput,
    StudySessionCreateInput,
)
from application.study.contracts.outputs import (
    ActiveStudySessionsOutput,
    DailyQuotaOutput,
    StudyLimitsOutput,
    StudyNoWorkOutput,
    StudyProgressOutput,
    StudySessionOpenedOutput,
    StudySessionOutput,
    StudySessionViewOutput,
    StudyStreakOutput,
)
from application.study.services.study import StudyService
from main import create_app


@pytest.fixture
def view() -> StudySessionViewOutput:
    now = datetime(2026, 11, 3, tzinfo=UTC)
    return StudySessionViewOutput(
        session=StudySessionOutput(
            id=1,
            deck_id=2,
            study_date=date(2026, 11, 3),
            status="active",
            started_at=now,
            last_activity_at=now,
            expires_at=now,
            finished_at=None,
            finish_reason=None,
            limits=StudyLimitsOutput(
                daily_total_cards_limit=125, daily_new_cards_limit=12
            ),
            progress=StudyProgressOutput(
                total_cards=1, completed_cards=0, remaining_cards=1
            ),
        ),
        current_card_id=3,
        answer_token="token",
        quota=DailyQuotaOutput(
            total_used=0, new_used=0, total_remaining=125, new_remaining=12
        ),
        streak=StudyStreakOutput(
            streak_days=0, max_streak_days=2, last_streak_date=None
        ),
        cards=[
            CardOutput(
                id=3,
                deck_id=2,
                front="q",
                back="a",
                hint=None,
                explanation=None,
                image_url=None,
                order_index=0,
                created_at=now,
                updated_at=now,
            )
        ],
    )


def test_input_and_nested_output_mappers(view: StudySessionViewOutput) -> None:
    assert to_session_create_input(
        OpenSessionRequest(deck_id=2)
    ) == StudySessionCreateInput(deck_id=2)
    assert to_review_create_input(
        ReviewRequest(card_id=3, rating=2, answer_token="token")
    ) == ReviewCreateInput(card_id=3, rating=2, answer_token="token")
    response = to_session_view_response(view)
    assert response.model_dump(mode="json") == view.model_dump(mode="json")
    assert to_review_response(view).model_dump(mode="json") == view.model_dump(
        mode="json", exclude={"cards"}
    )
    active = ActiveStudySessionsOutput(items=[view.session], total=1)
    assert to_active_sessions_response(active).model_dump(
        mode="json"
    ) == active.model_dump(mode="json")


@pytest.mark.parametrize(("created", "code"), [(True, 201), (False, 200)])
def test_open_session_mapping(
    view: StudySessionViewOutput, created: bool, code: int
) -> None:
    response, actual = to_open_session_response(
        StudySessionOpenedOutput(view=view, created=created)
    )
    assert actual == code
    assert response.model_dump(mode="json") == view.model_dump(mode="json")


@pytest.mark.parametrize("reason", ["empty_deck", "limits_reached", "nothing_due"])
def test_no_work_mapping(view: StudySessionViewOutput, reason: str) -> None:
    result = StudyNoWorkOutput.model_validate(
        {
            "deck_id": 2,
            "study_date": view.session.study_date,
            "limits": view.session.limits,
            "quota": view.quota,
            "streak": view.streak,
            "reason": reason,
        }
    )
    response, status = to_open_session_response(result)
    assert status == 200
    assert response.model_dump(mode="json") == {
        "session": None,
        "deck_id": 2,
        "study_date": "2026-11-03",
        "cards": [],
        "current_card_id": None,
        "answer_token": None,
        "limits": view.session.limits.model_dump(mode="json"),
        "quota": view.quota.model_dump(mode="json"),
        "streak": view.streak.model_dump(mode="json"),
        "reason": reason,
    }


async def test_routes_forward_typed_inputs_and_map_responses(
    view, profile, app_headers
) -> None:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    study = AsyncMock(spec=StudyService)
    study.open_session.return_value = StudySessionOpenedOutput(view=view, created=True)
    study.get_session.return_value = view
    study.list_active_sessions.return_value = ActiveStudySessionsOutput(
        items=[view.session], total=1
    )
    study.submit_review.return_value = view
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_study_service] = lambda: study
    headers = {**app_headers, "X-VK-User-ID": str(profile.vk_user_id)}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        opened = await client.post(
            "/api/v1/study/sessions", headers=headers, json={"deck_id": 2}
        )
        active = await client.get("/api/v1/study/sessions/active", headers=headers)
        session = await client.get("/api/v1/study/sessions/1", headers=headers)
        reviewed = await client.post(
            "/api/v1/study/sessions/1/reviews",
            headers=headers,
            json={"card_id": 3, "rating": 2, "answer_token": "token"},
        )
    assert opened.status_code == 201
    assert opened.json() == session.json() == view.model_dump(mode="json")
    assert active.status_code == 200 and active.json()["total"] == 1
    assert reviewed.status_code == 200 and "cards" not in reviewed.json()
    study.open_session.assert_awaited_once_with(
        profile.id, StudySessionCreateInput(deck_id=2)
    )
    study.submit_review.assert_awaited_once_with(
        profile.id, 1, ReviewCreateInput(card_id=3, rating=2, answer_token="token")
    )


def test_configured_study_segments_change_registered_paths() -> None:
    env = os.environ.copy()
    src = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (src, env.get("PYTHONPATH"))))
    env.update(
        {
            "APP_CONFIG__API__V1__STUDY": "/learning",
            "APP_CONFIG__API__V1__SESSIONS": "/rounds",
            "APP_CONFIG__API__V1__ACTIVE": "/ongoing",
            "APP_CONFIG__API__V1__REVIEWS": "/answers",
        }
    )
    code = """
from main import create_app
paths = create_app().openapi()["paths"]
assert "/api/v1/learning/rounds" in paths
assert "/api/v1/learning/rounds/ongoing" in paths
assert "/api/v1/learning/rounds/{session_id}" in paths
assert "/api/v1/learning/rounds/{session_id}/answers" in paths
assert "/api/v1/study/sessions" not in paths
"""
    subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
