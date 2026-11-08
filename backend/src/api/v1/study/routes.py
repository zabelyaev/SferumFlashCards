from fastapi import APIRouter, Response

from api.dependencies.auth import CurrentUserDep
from api.dependencies.services import StudyServiceDep
from api.types import BigIntId
from api.v1.study.contracts.mappers import (
    to_active_sessions_response,
    to_open_session_response,
    to_review_create_input,
    to_review_response,
    to_session_create_input,
    to_session_view_response,
)
from api.v1.study.contracts.requests import OpenSessionRequest, ReviewRequest
from api.v1.study.contracts.responses import (
    ActiveSessionsResponse,
    NoWorkResponse,
    ReviewResponse,
    SessionViewResponse,
)
from common.config import settings

router = APIRouter(
    prefix=f"{settings.api.v1.study}{settings.api.v1.sessions}", tags=["Study"]
)


@router.post(
    "",
    response_model=SessionViewResponse | NoWorkResponse,
    responses={201: {"model": SessionViewResponse}},
)
async def open_session(
    model: OpenSessionRequest,
    response: Response,
    user: CurrentUserDep,
    service: StudyServiceDep,
) -> SessionViewResponse | NoWorkResponse:
    body, response.status_code = to_open_session_response(
        await service.open_session(user.id, to_session_create_input(model))
    )
    return body


@router.get(settings.api.v1.active)
async def active_sessions(
    user: CurrentUserDep, service: StudyServiceDep
) -> ActiveSessionsResponse:
    return to_active_sessions_response(await service.list_active_sessions(user.id))


@router.get("/{session_id}")
async def get_session(
    session_id: BigIntId, user: CurrentUserDep, service: StudyServiceDep
) -> SessionViewResponse:
    return to_session_view_response(await service.get_session(user.id, session_id))


@router.post(f"/{{session_id}}{settings.api.v1.reviews}")
async def submit_review(
    session_id: BigIntId,
    model: ReviewRequest,
    user: CurrentUserDep,
    service: StudyServiceDep,
) -> ReviewResponse:
    return to_review_response(
        await service.submit_review(user.id, session_id, to_review_create_input(model))
    )
