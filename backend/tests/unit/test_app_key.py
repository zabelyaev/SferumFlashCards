import secrets

import pytest
from httpx import ASGITransport, AsyncClient

from application.accounts.auth.service import AuthService
from common.config import settings
from common.config.auth import AuthConfig
from common.exceptions.unauthorized import UnauthorizedError
from main import create_app


@pytest.mark.parametrize("supplied", [None, "", "wrong", "ключ"])
def test_auth_service_rejects_missing_and_wrong_app_keys(supplied: str | None) -> None:
    with pytest.raises(UnauthorizedError):
        AuthService("configured-key").require_app_key(supplied)


def test_auth_service_compares_using_constant_time(monkeypatch) -> None:
    calls: list[tuple[bytes, bytes]] = []
    compare = secrets.compare_digest

    def record(left: bytes, right: bytes) -> bool:
        calls.append((left, right))
        return compare(left, right)

    monkeypatch.setattr(secrets, "compare_digest", record)
    service = AuthService("configured-key")
    service.require_app_key("configured-key")
    with pytest.raises(UnauthorizedError):
        service.require_app_key(None)
    assert calls == [(b"configured-key", b"configured-key"), (b"", b"configured-key")]


def test_auth_service_rejects_an_empty_configured_key() -> None:
    with pytest.raises(ValueError, match="empty"):
        AuthService("")


def test_application_fails_fast_when_no_app_key_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth", AuthConfig())
    with pytest.raises(RuntimeError, match="APP_CONFIG__AUTH__APP_KEY"):
        create_app()


@pytest.mark.parametrize("headers", [{}, {"X-App-Key": "wrong"}])
async def test_invalid_key_is_rejected_without_database_state(headers) -> None:
    app = create_app()
    assert not hasattr(app.state, "database_helper")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/users/sync", headers=headers, json={"vk_user_id": 12345678}
        )
    assert response.status_code == 401
