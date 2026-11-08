from typing import TYPE_CHECKING

from fastapi import status
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import Request

    from common.exceptions.unauthorized import UnauthorizedError


async def handler(request: Request, exc: UnauthorizedError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": exc.detail}
    )
