from fastapi import APIRouter, status

from api.dependencies.services import UserServiceDep
from api.v1.users.contracts.mappers import to_user_profile_response, to_user_sync_input
from api.v1.users.contracts.requests import UserSyncRequest
from api.v1.users.contracts.responses import UserProfileResponse
from common.config import settings

router = APIRouter()


@router.post(settings.api.v1.sync, status_code=status.HTTP_200_OK)
async def sync_user(
    model: UserSyncRequest, service: UserServiceDep
) -> UserProfileResponse:
    user = await service.sync(to_user_sync_input(model))
    return to_user_profile_response(user)
