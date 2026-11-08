from fastapi import APIRouter

from api.dependencies.auth import CurrentUserDep
from api.dependencies.services import UserServiceDep
from api.v1.users.contracts.mappers import (
    to_user_profile_response,
    to_user_settings_replace_input,
)
from api.v1.users.contracts.requests import UserSettingsReplaceRequest
from api.v1.users.contracts.responses import UserProfileResponse
from common.config import settings

router = APIRouter(prefix=f"{settings.api.v1.me}{settings.api.v1.settings}")


@router.put("")
async def replace_settings(
    model: UserSettingsReplaceRequest,
    current_user: CurrentUserDep,
    service: UserServiceDep,
) -> UserProfileResponse:
    user = await service.replace_settings(
        current_user.id, to_user_settings_replace_input(model)
    )
    return to_user_profile_response(user)
