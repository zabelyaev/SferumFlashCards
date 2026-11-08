from typing import TYPE_CHECKING

from fastapi import status
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import Request

    from common.exceptions.conflict import ConflictError


async def handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": exc.detail},
    )
