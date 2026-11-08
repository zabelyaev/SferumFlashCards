import json
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from api.dependencies.services import get_user_service
from api.v1.users.contracts.requests import UserSettingsReplaceRequest
from application.accounts.users.contracts.inputs import UserSettingsReplaceInput
from application.accounts.users.service import UserService
from common.exceptions.handlers.validation import handler
from common.schemas.json_values import validate_postgres_json
from main import create_app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import Request


@pytest_asyncio.fixture
async def validation_client(
    profile, user_headers
) -> AsyncIterator[tuple[AsyncClient, AsyncMock]]:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    users.get_profile.return_value = profile

    async def replace_settings(user_id, model):
        return profile.model_copy(update={"settings": model.settings})

    users.replace_settings.side_effect = replace_settings
    app.dependency_overrides[get_user_service] = lambda: users
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=user_headers,
    ) as client:
        yield client, users


def nested_json(kind: str, depth: int) -> bytes:
    opening, closing = (b"[", b"]") if kind == "list" else (b'{"x":', b"}")
    return b'{"x":' + opening * depth + b"0" + closing * depth + b"}"


@pytest.mark.parametrize("kind", ["list", "dict"])
@pytest.mark.parametrize("depth", [254, 255, 1500, 10_000])
async def test_deep_settings_are_rejected_without_crashing(
    validation_client, kind, depth
) -> None:
    client, users = validation_client
    response = await client.put(
        "/api/v1/users/me/settings",
        content=nested_json(kind, depth),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert errors
    expected_type = "value_error" if depth == 254 else "recursion_loop"
    assert any(error["type"] == expected_type for error in errors)
    assert all(set(error) == {"type", "loc", "msg"} for error in errors)
    users.replace_settings.assert_not_awaited()

    healthy = await client.get("/api/v1/users/me/profile")
    assert healthy.status_code == 200
    accepted = await client.put(
        "/api/v1/users/me/settings", json={"theme": "dark", "nested": [1, None]}
    )
    assert accepted.status_code == 200
    users.replace_settings.assert_awaited_once()
    assert users.replace_settings.await_args.args[1].settings == {
        "theme": "dark",
        "nested": [1, None],
    }


@pytest.mark.parametrize("kind", ["list", "dict"])
@pytest.mark.parametrize("depth", [150, 253])
async def test_valid_nested_settings_are_unchanged(
    validation_client, kind, depth
) -> None:
    client, users = validation_client
    payload = nested_json(kind, depth)
    response = await client.put(
        "/api/v1/users/me/settings",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["settings"] == json.loads(payload)
    assert users.replace_settings.await_args.args[1].settings == json.loads(payload)


@pytest.mark.parametrize("kind", ["list", "dict"])
def test_settings_depth_limit_also_applies_to_application_inputs(kind) -> None:
    accepted = json.loads(nested_json(kind, 253))
    rejected = json.loads(nested_json(kind, 254))
    assert UserSettingsReplaceInput(settings=accepted).settings == accepted
    with pytest.raises(ValidationError, match="253 nested containers"):
        UserSettingsReplaceInput(settings=rejected)
    with pytest.raises(ValidationError, match="253 nested containers"):
        UserSettingsReplaceRequest.model_validate(rejected)


def test_json_depth_check_counts_containers_not_scalar_leaves() -> None:
    value = [0, True, None, "text", 1.5]
    for _ in range(252):
        value = [value]
    validate_postgres_json({"x": value})
    with pytest.raises(ValueError, match="253 nested containers"):
        validate_postgres_json({"x": [value]})


def test_json_depth_limit_applies_to_mixed_and_empty_containers() -> None:
    value = {}
    for index in range(252):
        value = [value] if index % 2 else {"x": value}
    validate_postgres_json({"deep": value, "shallow": [[], {}]})
    with pytest.raises(ValueError, match="253 nested containers"):
        validate_postgres_json({"deep": [value]})


@pytest.mark.parametrize(
    "payload",
    [
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":-Infinity}',
        b'{"x":"\\ud800"}',
        b'{"\\udfff":"value"}',
        b'{"x":"\\u0000"}',
        b"[]",
    ],
)
async def test_invalid_settings_values_have_safe_error_details(
    validation_client, payload
) -> None:
    client, users = validation_client
    response = await client.put(
        "/api/v1/users/me/settings",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert errors
    assert all(set(error) == {"type", "loc", "msg"} for error in errors)
    users.replace_settings.assert_not_awaited()


async def test_handler_never_serializes_input_or_context() -> None:
    circular: dict[str, object] = {}
    circular["self"] = circular
    error = RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", "name\ud800", 2),
                "msg": "Invalid text \udfff",
                "input": circular,
                "ctx": {"error": ValueError("private context"), "value": circular},
                "url": "https://errors.example.invalid",
            }
        ]
    )
    response = await handler(cast("Request", None), error)
    assert response.status_code == 422
    assert json.loads(bytes(response.body)) == {
        "detail": [
            {
                "type": "value_error",
                "loc": ["body", r"name\ud800", 2],
                "msg": r"Invalid text \udfff",
            }
        ]
    }


@pytest.mark.parametrize(
    ("path", "payload", "location", "error_type"),
    [
        ("/api/v1/users/sync", {}, ["body", "vk_user_id"], "missing"),
        (
            "/api/v1/users/me/profile",
            {"daily_new_cards_limit": 0},
            ["body", "daily_new_cards_limit"],
            "greater_than_equal",
        ),
    ],
)
async def test_ordinary_validation_errors_keep_type_location_and_message(
    validation_client, path, payload, location, error_type
) -> None:
    client, users = validation_client
    method = "POST" if path.endswith("/sync") else "PATCH"
    response = await client.request(method, path, json=payload)
    assert response.status_code == 422
    assert any(
        error["type"] == error_type
        and error["loc"][: len(location)] == location
        and isinstance(error["msg"], str)
        for error in response.json()["detail"]
    )
    users.sync.assert_not_awaited()
    users.update.assert_not_awaited()


async def test_deep_settings_do_not_bypass_authentication(validation_client) -> None:
    client, users = validation_client
    response = await client.put(
        "/api/v1/users/me/settings",
        content=nested_json("list", 1500),
        headers={"Content-Type": "application/json", "X-App-Key": "wrong"},
    )
    assert response.status_code == 401
    users.get_current.assert_not_awaited()
    users.replace_settings.assert_not_awaited()
