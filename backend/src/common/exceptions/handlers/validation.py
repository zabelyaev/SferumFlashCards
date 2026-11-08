from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import Request
    from fastapi.exceptions import RequestValidationError


def _safe_text(value: str) -> str:
    return value.encode("utf-8", errors="backslashreplace").decode("utf-8")


async def handler(_request: Request, exc: RequestValidationError) -> JSONResponse:

    errors = [
        {
            "type": _safe_text(error["type"]),
            "loc": [
                _safe_text(part) if isinstance(part, str) else part
                for part in error["loc"]
            ],
            "msg": _safe_text(error["msg"]),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})
