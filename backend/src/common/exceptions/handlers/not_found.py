from typing import TYPE_CHECKING

from fastapi import status
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import Request

    from common.exceptions.not_found import NotFoundError


async def handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": exc.detail},
    )
