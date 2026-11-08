from typing import Annotated

from fastapi import Depends, Header, Security
from fastapi.security import APIKeyHeader

from api.dependencies.services import AuthServiceDep, UserServiceDep
from api.types import BIGINT_MAX, BigIntId
from api.v1.headers import APP_KEY_HEADER, VK_USER_ID_HEADER
from application.accounts.users.contracts.outputs import CurrentUserOutput

app_key_header = APIKeyHeader(
    name=APP_KEY_HEADER, scheme_name="AppKey", auto_error=False
)


def require_app_key(
    app_key: Annotated[str | None, Security(app_key_header)],
    auth_service: AuthServiceDep,
) -> None:
    auth_service.require_app_key(app_key)


async def get_current_user(
    vk_user_id: Annotated[
        BigIntId,
        Header(
            alias=VK_USER_ID_HEADER,
            description="VK user ID.",
            json_schema_extra={"maximum": BIGINT_MAX},
        ),
    ],
    user_service: UserServiceDep,
) -> CurrentUserOutput:
    return await user_service.get_current(vk_user_id)


type CurrentUserDep = Annotated[CurrentUserOutput, Depends(get_current_user)]
