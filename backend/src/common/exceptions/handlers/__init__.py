from typing import TYPE_CHECKING

from fastapi.exceptions import RequestValidationError

from common.exceptions.conflict import ConflictError
from common.exceptions.forbidden import ForbiddenError
from common.exceptions.not_found import NotFoundError
from common.exceptions.unauthorized import UnauthorizedError

from .conflict import handler as conflict_handler
from .forbidden import handler as forbidden_handler
from .not_found import handler as not_found_handler
from .unauthorized import handler as unauthorized_handler
from .validation import handler as validation_handler

if TYPE_CHECKING:
    from fastapi import FastAPI


def mount_exceptions_handlers(app: FastAPI) -> None:
    app.add_exception_handler(NotFoundError, not_found_handler)  # type: ignore
    app.add_exception_handler(UnauthorizedError, unauthorized_handler)  # type: ignore
    app.add_exception_handler(ForbiddenError, forbidden_handler)  # type: ignore
    app.add_exception_handler(ConflictError, conflict_handler)  # type: ignore
    app.add_exception_handler(RequestValidationError, validation_handler)  # type: ignore
