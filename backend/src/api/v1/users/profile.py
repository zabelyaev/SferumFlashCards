from fastapi import APIRouter, status

from api.dependencies.auth import CurrentUserDep
from api.dependencies.services import UserServiceDep
from api.v1.users.contracts.mappers import (
    to_user_profile_response,
    to_user_profile_update_input,
)
from api.v1.users.contracts.requests import UserProfileUpdateRequest
from api.v1.users.contracts.responses import UserProfileResponse
from common.config import settings

router = APIRouter(prefix=f"{settings.api.v1.me}{settings.api.v1.profile}")


@router.get("", status_code=status.HTTP_200_OK)
async def read_profile(
    current_user: CurrentUserDep, user_service: UserServiceDep
) -> UserProfileResponse:
    return to_user_profile_response(await user_service.get_profile(current_user.id))


@router.patch("", status_code=status.HTTP_200_OK)
async def update_profile(
    model: UserProfileUpdateRequest,
    user_service: UserServiceDep,
    current_user: CurrentUserDep,
) -> UserProfileResponse:
    user = await user_service.update(
        current_user.id, to_user_profile_update_input(model)
    )
    return to_user_profile_response(user)
