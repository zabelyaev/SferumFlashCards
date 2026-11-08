import secrets

from common.exceptions.unauthorized import UnauthorizedError


class AuthService:
    def __init__(self, app_key: str) -> None:
        if not app_key:
            raise ValueError("App key must not be empty.")
        self._app_key = app_key

    def require_app_key(self, supplied: str | None) -> None:
        if not secrets.compare_digest(
            (supplied or "").encode(), self._app_key.encode()
        ):
            raise UnauthorizedError("Invalid application key.")
