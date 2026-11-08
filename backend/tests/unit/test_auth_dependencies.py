import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.dependencies.services import get_user_service
from application.accounts.users.contracts.inputs import (
    UserProfileUpdateInput,
    UserSettingsReplaceInput,
    UserSyncInput,
)
from application.accounts.users.service import UserService
from common.exceptions.forbidden import ForbiddenError
from common.exceptions.unauthorized import UnauthorizedError
from main import main_app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

PROFILE_PATH = "/api/v1/users/me/profile"
SYNC_PATH = "/api/v1/users/sync"
VK_HEADERS = {"X-VK-User-ID": "12345678"}


@pytest.fixture
def services(profile):
    users = AsyncMock(spec=UserService)
    users.sync.return_value = profile
    users.get_current.return_value = profile
    users.get_profile.return_value = profile
    users.update.return_value = profile
    users.replace_settings.return_value = profile
    return users


@pytest_asyncio.fixture
async def client(services) -> AsyncIterator[AsyncClient]:
    main_app.dependency_overrides[get_user_service] = lambda: services
    try:
        async with AsyncClient(
            transport=ASGITransport(app=main_app), base_url="http://test"
        ) as client:
            yield client
    finally:
        main_app.dependency_overrides.clear()


@pytest.mark.parametrize("invalid", [None, "wrong-key"])
async def test_app_key_is_required_before_any_user_operation(
    client, services, app_headers, invalid: str | None
) -> None:
    headers = app_headers.copy()
    if invalid is None:
        del headers["X-App-Key"]
    else:
        headers["X-App-Key"] = invalid
    response = await client.post(
        SYNC_PATH, headers=headers, json={"vk_user_id": 12345678}
    )
    assert response.status_code == 401
    response = await client.get(PROFILE_PATH, headers={**headers, **VK_HEADERS})
    assert response.status_code == 401
    services.sync.assert_not_awaited()
    services.get_current.assert_not_awaited()


async def test_old_keys_cannot_replace_the_app_key(client, services) -> None:
    response = await client.post(
        SYNC_PATH,
        headers={"X-Client-Key": "old-client", "X-Access-Key": "old-access"},
        json={"vk_user_id": 12345678},
    )
    assert response.status_code == 401
    services.sync.assert_not_awaited()


async def test_sync_returns_profile_without_tokens(
    client, services, app_headers
) -> None:
    response = await client.post(
        SYNC_PATH,
        headers=app_headers,
        json={"vk_user_id": 12345678, "first_name": "  Иван  "},
    )
    assert response.status_code == 200
    assert response.json()["vk_user_id"] == 12345678
    assert response.json()["id"] == 7
    assert "access_token" not in response.json()
    request = services.sync.await_args.args[0]
    assert type(request) is UserSyncInput
    assert request.model_fields_set == {"vk_user_id", "first_name"}
    assert request.vk_user_id == 12345678
    assert request.first_name == "Иван"
    services.get_current.assert_not_awaited()


@pytest.mark.parametrize(
    ("vk_id", "expected"),
    [("12345678", 12345678), ("9223372036854775807", 2**63 - 1), (1.0, 1), (True, 1)],
)
async def test_sync_coerces_valid_ids_in_json(
    client, services, app_headers, vk_id, expected
) -> None:
    response = await client.post(
        SYNC_PATH, headers=app_headers, json={"vk_user_id": vk_id}
    )
    assert response.status_code == 200
    request = services.sync.await_args.args[0]
    assert type(request.vk_user_id) is int and request.vk_user_id == expected


@pytest.mark.parametrize("vk_id", [0, -1, False, 1.5, "abc", 2**63])
async def test_sync_rejects_invalid_ids_in_json(
    client, services, app_headers, vk_id
) -> None:
    response = await client.post(
        SYNC_PATH, headers=app_headers, json={"vk_user_id": vk_id}
    )
    assert response.status_code == 422
    services.sync.assert_not_awaited()


async def test_profile_resolves_vk_id_from_header(
    client, services, user_headers
) -> None:
    response = await client.get(PROFILE_PATH, headers=user_headers)
    assert response.status_code == 200
    users = services
    users.get_current.assert_awaited_once_with(12345678)
    assert response.json() == users.get_current.return_value.model_dump(mode="json")


@pytest.mark.parametrize("header_name", ["x-vk-user-id", "X-VK-USER-ID"])
async def test_vk_header_name_is_case_insensitive(
    client, services, app_headers, header_name
) -> None:
    response = await client.get(
        PROFILE_PATH, headers={**app_headers, header_name: "12345678"}
    )
    assert response.status_code == 200
    services.get_current.assert_awaited_once_with(12345678)


@pytest.mark.parametrize(
    ("vk_id", "expected"), [("1", 1), ("01", 1), ("+1", 1), ("1.0", 1)]
)
async def test_profile_header_uses_standard_integer_parsing(
    client, services, app_headers, vk_id, expected
) -> None:
    response = await client.get(
        PROFILE_PATH, headers={**app_headers, "X-VK-User-ID": vk_id}
    )
    assert response.status_code == 200
    services.get_current.assert_awaited_once_with(expected)


@pytest.mark.parametrize("method", ["GET", "PATCH"])
@pytest.mark.parametrize(
    "vk_id", ["", "0", "-1", "abc", "1.5", "1e0", "9223372036854775808"]
)
async def test_invalid_vk_header_id_is_rejected(
    client, services, app_headers, method, vk_id
) -> None:
    response = await client.request(
        method,
        PROFILE_PATH,
        headers={**app_headers, "X-VK-User-ID": vk_id},
        json={"first_name": "Анна"} if method == "PATCH" else None,
    )
    assert response.status_code == 422
    assert any(
        error["loc"] == ["header", "X-VK-User-ID"]
        for error in response.json()["detail"]
    )
    users = services
    users.get_current.assert_not_awaited()
    users.update.assert_not_awaited()
    users.delete.assert_not_awaited()


@pytest.mark.parametrize("method", ["GET", "PATCH"])
@pytest.mark.parametrize("params", [{}, {"id": "12345678"}, {"vk_user_id": "12345678"}])
async def test_vk_user_id_header_is_required_for_all_profile_operations(
    client, services, app_headers, method, params
) -> None:
    response = await client.request(
        method,
        PROFILE_PATH,
        params=params,
        headers=app_headers,
        json={"first_name": "Анна"} if method == "PATCH" else None,
    )
    assert response.status_code == 422
    assert any(
        error["loc"] == ["header", "X-VK-User-ID"] and error["type"] == "missing"
        for error in response.json()["detail"]
    )
    users = services
    users.get_current.assert_not_awaited()
    users.update.assert_not_awaited()
    users.delete.assert_not_awaited()


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
async def test_old_vk_id_path_is_not_available(
    client, services, user_headers, method
) -> None:
    response = await client.request(
        method,
        "/api/v1/users/12345678/profile",
        headers=user_headers,
        json={"first_name": "Анна"} if method == "PATCH" else None,
    )
    assert response.status_code == 404
    users = services
    users.get_current.assert_not_awaited()
    users.update.assert_not_awaited()
    users.delete.assert_not_awaited()


async def test_header_vk_id_preserves_bigint_precision(
    client, services, app_headers
) -> None:
    response = await client.get(
        PROFILE_PATH, headers={**app_headers, "X-VK-User-ID": "9223372036854775807"}
    )
    assert response.status_code == 200
    users = services
    users.get_current.assert_awaited_once_with(2**63 - 1)


async def test_vk_id_in_body_does_not_replace_required_header(
    client, services, app_headers
) -> None:
    response = await client.patch(
        PROFILE_PATH,
        headers=app_headers,
        json={"vk_user_id": "12345678", "first_name": "Анна"},
    )
    assert response.status_code == 422
    assert any(
        error["loc"] == ["header", "X-VK-User-ID"]
        for error in response.json()["detail"]
    )
    users = services
    users.get_current.assert_not_awaited()
    users.update.assert_not_awaited()


async def test_sync_requires_vk_id_in_body(client, services, user_headers) -> None:
    response = await client.post(
        SYNC_PATH, params={"vk_user_id": "12345678"}, headers=user_headers, json={}
    )
    assert response.status_code == 422
    services.sync.assert_not_awaited()
    services.get_current.assert_not_awaited()


async def test_sync_uses_body_even_if_user_header_is_present(
    client, services, app_headers
) -> None:
    response = await client.post(
        SYNC_PATH,
        headers={**app_headers, "X-VK-User-ID": "999"},
        json={"vk_user_id": 12345678},
    )
    assert response.status_code == 200
    assert services.sync.await_args.args[0].vk_user_id == 12345678
    services.get_current.assert_not_awaited()


async def test_header_takes_precedence_over_obsolete_query(
    client, services, user_headers
) -> None:
    response = await client.get(
        PROFILE_PATH, params={"vk_user_id": "42"}, headers=user_headers
    )
    assert response.status_code == 200
    services.get_current.assert_awaited_once_with(12345678)


async def test_old_login_path_is_not_available(client, services, app_headers) -> None:
    response = await client.post(
        "/api/v1/auth/login", headers=app_headers, json={"vk_user_id": "12345678"}
    )
    assert response.status_code == 404
    services.sync.assert_not_awaited()


async def test_profile_update_uses_internal_id_and_preserves_explicit_null(
    client, services, user_headers
) -> None:
    response = await client.patch(
        PROFILE_PATH,
        headers=user_headers,
        json={"first_name": "Анна", "avatar_url": None},
    )
    assert response.status_code == 200
    users = services
    user_id, update = users.update.await_args.args
    assert user_id == 7
    assert type(update) is UserProfileUpdateInput
    assert update.model_dump(exclude_unset=True) == {
        "first_name": "Анна",
        "avatar_url": None,
    }


async def test_profile_update_passes_timezone_and_daily_limit(
    client, services, user_headers
) -> None:
    response = await client.patch(
        PROFILE_PATH,
        headers=user_headers,
        json={"timezone": "Europe/Moscow", "daily_new_cards_limit": 30},
    )
    assert response.status_code == 200
    user_id, update = services.update.await_args.args
    assert user_id == 7
    assert type(update) is UserProfileUpdateInput
    assert update.model_dump(exclude_unset=True) == {
        "timezone": "Europe/Moscow",
        "daily_new_cards_limit": 30,
    }


@pytest.mark.parametrize("field", ["first_name", "last_name", "timezone"])
async def test_profile_update_rejects_null_for_optional_fields(
    client, services, user_headers, field: str
) -> None:
    response = await client.patch(
        PROFILE_PATH, headers=user_headers, json={field: None}
    )
    assert response.status_code == 422
    services.update.assert_not_awaited()


@pytest.mark.parametrize("field", ["first_name", "last_name"])
@pytest.mark.parametrize("bad_name", ["A\x00B", "A\ud800B"])
async def test_sync_rejects_postgres_incompatible_names(
    client, services, app_headers, field, bad_name
) -> None:
    response = await client.post(
        SYNC_PATH,
        headers={**app_headers, "Content-Type": "application/json"},
        content=json.dumps({"vk_user_id": 12345678, field: bad_name}),
    )
    assert response.status_code == 422
    assert field in response.json()["detail"][0]["loc"]
    services.sync.assert_not_awaited()


@pytest.mark.parametrize("field", ["first_name", "last_name"])
@pytest.mark.parametrize("bad_name", ["A\x00B", "A\ud800B"])
async def test_profile_update_rejects_postgres_incompatible_names(
    client, services, user_headers, field, bad_name
) -> None:
    response = await client.patch(
        PROFILE_PATH,
        headers={**user_headers, "Content-Type": "application/json"},
        content=json.dumps({field: bad_name}),
    )
    assert response.status_code == 422
    assert field in response.json()["detail"][0]["loc"]
    services.update.assert_not_awaited()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
async def test_validation_error_serializes_nonfinite_values(
    client, services, user_headers, value
) -> None:
    response = await client.patch(
        PROFILE_PATH,
        headers={**user_headers, "Content-Type": "application/json"},
        content=json.dumps({"daily_total_cards_limit": value}),
    )
    assert response.status_code == 422
    assert "daily_total_cards_limit" in response.json()["detail"][0]["loc"]
    services.update.assert_not_awaited()


async def test_settings_validation_error_serializes_nested_invalid_values(
    client, services, user_headers
) -> None:
    payload = {"nested": [{"bad\ud800key": float("nan")}], "bad\ud800key": "x"}
    response = await client.put(
        "/api/v1/users/me/settings",
        headers={**user_headers, "Content-Type": "application/json"},
        content=json.dumps(payload),
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    services.replace_settings.assert_not_awaited()


async def test_settings_treats_timezone_and_daily_limit_as_arbitrary_json(
    client, services, user_headers
) -> None:
    data = {"timezone": None, "daily_cards_limit": {"value": 500}, "theme": "custom"}
    response = await client.put(
        "/api/v1/users/me/settings", headers=user_headers, json=data
    )
    assert response.status_code == 200
    user_id, update = services.replace_settings.await_args.args
    assert user_id == 7
    assert type(update) is UserSettingsReplaceInput
    assert update.settings == data


@pytest.mark.parametrize(
    ("field", "limit", "error_type"),
    [
        (field, limit, error_type)
        for field, values in (
            (
                "daily_total_cards_limit",
                [
                    (19, "greater_than_equal"),
                    (1001, "less_than_equal"),
                    (None, "value_error"),
                    (True, "int_type"),
                    ("20", "int_type"),
                    (20.0, "int_type"),
                ],
            ),
            (
                "daily_new_cards_limit",
                [
                    (0, "greater_than_equal"),
                    (251, "less_than_equal"),
                    (None, "value_error"),
                    (True, "int_type"),
                    ("12", "int_type"),
                    (12.0, "int_type"),
                ],
            ),
        )
        for limit, error_type in values
    ],
)
async def test_profile_update_rejects_invalid_daily_limit(
    client, services, user_headers, field, limit, error_type
) -> None:
    response = await client.patch(
        PROFILE_PATH,
        headers=user_headers,
        json={field: limit},
    )
    assert response.status_code == 422
    assert any(
        error["type"] == error_type
        and (field in error["loc"] if limit is not None else field in error["msg"])
        for error in response.json()["detail"]
    )
    services.update.assert_not_awaited()


@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("daily_total_cards_limit", 20),
        ("daily_total_cards_limit", 1000),
        ("daily_new_cards_limit", 1),
        ("daily_new_cards_limit", 250),
    ],
)
async def test_profile_update_accepts_daily_limit_boundaries(
    client, services, user_headers, field, limit
) -> None:
    response = await client.patch(
        PROFILE_PATH, headers=user_headers, json={field: limit}
    )
    assert response.status_code == 200
    assert services.update.await_args.args[1].model_dump(exclude_unset=True) == {
        field: limit
    }


async def test_profile_update_rejects_removed_daily_limit(
    client, services, user_headers
) -> None:
    response = await client.patch(
        PROFILE_PATH, headers=user_headers, json={"daily_cards_limit": 20}
    )
    assert response.status_code == 422
    assert any(
        error["type"] == "extra_forbidden" and error["loc"][-1] == "daily_cards_limit"
        for error in response.json()["detail"]
    )
    services.update.assert_not_awaited()


@pytest.mark.parametrize("field", ["vk_user_id", "role", "is_active", "id", "password"])
async def test_profile_update_rejects_server_owned_fields(
    client, services, user_headers, field
) -> None:
    response = await client.patch(
        PROFILE_PATH, headers=user_headers, json={field: "value"}
    )
    assert response.status_code == 422
    users = services
    users.update.assert_not_awaited()


async def test_unknown_user_must_sync_first(client, services, user_headers) -> None:
    users = services
    users.get_current.side_effect = UnauthorizedError("Sign in first.")
    response = await client.get(PROFILE_PATH, headers=user_headers)
    assert response.status_code == 401


async def test_disabled_user_is_forbidden(client, services, user_headers) -> None:
    users = services
    users.get_current.side_effect = ForbiddenError("User is disabled.")
    response = await client.get(PROFILE_PATH, headers=user_headers)
    assert response.status_code == 403


async def test_delete_profile_is_temporarily_disabled(
    client, services, user_headers
) -> None:
    response = await client.delete(PROFILE_PATH, headers=user_headers)
    assert response.status_code == 405
    users = services
    users.delete.assert_not_awaited()


async def test_cors_preflight_does_not_require_keys(client, services) -> None:
    response = await client.options(
        SYNC_PATH,
        headers={
            "Origin": "https://presentation.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-App-Key,Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    services.sync.assert_not_awaited()
    services.get_current.assert_not_awaited()


async def test_cors_preflight_allows_vk_user_header(client, services) -> None:
    response = await client.options(
        "/api/v1/decks",
        headers={
            "Origin": "https://presentation.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-App-Key,X-VK-User-ID,Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "x-vk-user-id" in response.headers["access-control-allow-headers"].lower()
    services.get_current.assert_not_awaited()


async def test_cors_allows_request_with_vk_user_header(
    client, services, user_headers
) -> None:
    response = await client.get(
        PROFILE_PATH, headers={**user_headers, "Origin": "https://presentation.example"}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    services.get_current.assert_awaited_once_with(12345678)


async def test_cors_preflight_rejects_removed_key_headers(client, services) -> None:
    response = await client.options(
        SYNC_PATH,
        headers={
            "Origin": "https://presentation.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-App-Key,X-Client-Key,X-Access-Key",
        },
    )
    assert response.status_code == 400
    services.sync.assert_not_awaited()
