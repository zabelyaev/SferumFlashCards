from typing import TYPE_CHECKING, cast

from common.exceptions.forbidden import ForbiddenError
from common.exceptions.handlers.forbidden import handler as forbidden_handler
from common.exceptions.handlers.unauthorized import handler as unauthorized_handler
from common.exceptions.unauthorized import UnauthorizedError

if TYPE_CHECKING:
    from fastapi import Request


async def test_unauthorized_has_no_bearer_challenge() -> None:
    response = await unauthorized_handler(cast("Request", None), UnauthorizedError())
    assert response.status_code == 401
    assert "www-authenticate" not in response.headers


async def test_forbidden_returns_403() -> None:
    response = await forbidden_handler(cast("Request", None), ForbiddenError())
    assert response.status_code == 403
