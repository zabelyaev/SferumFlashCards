import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from api.dependencies.services import (
    get_card_service,
    get_deck_service,
    get_library_service,
    get_user_service,
)
from api.v1.flashcards.cards.contracts.mappers import to_card_update_input
from api.v1.flashcards.cards.contracts.requests import CardUpdateRequest
from api.v1.flashcards.decks.contracts.mappers import to_deck_update_input
from api.v1.flashcards.decks.contracts.requests import DeckUpdateRequest
from api.v1.users.contracts.mappers import to_user_settings_replace_input
from api.v1.users.contracts.requests import UserSettingsReplaceRequest
from application.accounts.users.contracts.inputs import UserSettingsReplaceInput
from application.accounts.users.service import UserService
from application.flashcards.cards.service import CardService
from application.flashcards.decks.contracts.outputs import (
    DeckCatalogOutput,
    DeckOutput,
    DeckSharePreviewOutput,
)
from application.flashcards.decks.service import DeckService
from application.flashcards.library.contracts.inputs import LibraryListInput
from application.flashcards.library.contracts.outputs import LibraryListOutput
from application.flashcards.library.service import LibraryService
from common.exceptions.forbidden import ForbiddenError
from common.exceptions.unauthorized import UnauthorizedError
from main import create_app


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (DeckUpdateRequest, {}),
        (DeckUpdateRequest, {"title": None}),
        (DeckUpdateRequest, {"title": "   "}),
        (DeckUpdateRequest, {"author_id": 3}),
        (DeckUpdateRequest, {"is_official": True}),
        (DeckUpdateRequest, {"grade": 12}),
        (DeckUpdateRequest, {"description": "bad\x00text"}),
        (DeckUpdateRequest, {"title": "bad\x00text"}),
        (DeckUpdateRequest, {"cover_color": "bad\x00text"}),
        (CardUpdateRequest, {}),
        (CardUpdateRequest, {"front": None}),
        (CardUpdateRequest, {"back": "  "}),
        (CardUpdateRequest, {"order_index": 1}),
        (CardUpdateRequest, {"deck_id": 2}),
        (CardUpdateRequest, {"front": "bad\x00text"}),
        (CardUpdateRequest, {"hint": "bad\x00text"}),
    ],
)
def test_update_schemas_reject_invalid_and_server_owned_fields(schema, payload) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_update_mappers_keep_explicit_null_and_omissions() -> None:
    deck = to_deck_update_input(DeckUpdateRequest(description=None, subject="physics"))
    assert deck.model_fields_set == {"description", "subject"}
    assert deck.description is None and deck.subject == "physics"
    card = to_card_update_input(CardUpdateRequest(hint=None))
    assert card.model_dump(exclude_unset=True) == {"hint": None}


@pytest.mark.parametrize(
    "payload",
    [
        {
            "timezone": "Europe/Moscow",
            "daily_cards_limit": 30,
            "role": "admin",
            "custom": {"array": [1, None, True, "text"]},
        },
        {"timezone": "Mars/Olympus", "daily_cards_limit": 51},
        {"timezone": None, "daily_cards_limit": {"custom": [True, None]}},
        {"root": "ordinary setting", "__pydantic_extra__": {"nested": [1, None]}},
    ],
)
def test_settings_mapper_keeps_all_json_fields_as_is(payload) -> None:
    request = UserSettingsReplaceRequest.model_validate(payload)
    assert request.model_dump(mode="json") == payload
    mapped = to_user_settings_replace_input(request)
    assert mapped.settings == payload
    assert mapped.model_fields_set == {"settings"}
    assert to_user_settings_replace_input(UserSettingsReplaceRequest()).settings == {}
    assert to_user_settings_replace_input(
        UserSettingsReplaceRequest()
    ).model_fields_set == {"settings"}


@pytest.mark.parametrize(
    "data",
    [
        {"unknown": {"nested": "x\x00y"}},
        {"unknown": {"bad\x00key": 1}},
        {"unknown": [float("nan")]},
        {"unknown": "\ud800"},
    ],
)
def test_settings_replacement_validates_json_storage(data) -> None:
    with pytest.raises(ValidationError):
        UserSettingsReplaceRequest.model_validate(data)


@pytest.mark.parametrize("data", [None, [], [1, 2], "text", 42])
def test_settings_replacement_requires_a_json_object(data) -> None:
    with pytest.raises(ValidationError):
        UserSettingsReplaceRequest.model_validate(data)


@pytest.mark.parametrize("settings", [{"x": "\x00"}, {"x": float("inf")}])
def test_application_settings_also_reject_invalid_postgres_json(settings) -> None:
    with pytest.raises(ValidationError):
        UserSettingsReplaceInput(settings=settings)


async def test_settings_endpoint_preserves_flat_json_object(
    user_headers, profile
) -> None:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    users.replace_settings.return_value = profile
    app.dependency_overrides[get_user_service] = lambda: users
    payload = {"root": "ordinary key", "custom": {"values": [1, None, True]}}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put(
            "/api/v1/users/me/settings",
            headers=user_headers,
            json=payload,
        )
        assert response.status_code == 200
        user_id, settings = users.replace_settings.await_args.args
        assert user_id == profile.id
        assert settings.settings == payload

        users.replace_settings.reset_mock()
        response = await client.put(
            "/api/v1/users/me/settings",
            headers=user_headers,
            json=[1, 2],
        )
        assert response.status_code == 422
        users.replace_settings.assert_not_awaited()


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/decks", None),
        ("PATCH", "/api/v1/decks/1", {"title": "x"}),
        ("PATCH", "/api/v1/decks/1/cards/2", {"front": "x"}),
        ("GET", "/api/v1/decks/share/Abc123_-", None),
        ("PUT", "/api/v1/library/decks/share/Abc123_-", None),
        ("PUT", "/api/v1/users/me/settings", {}),
    ],
)
async def test_new_routes_require_app_key_and_vk_id(
    method, path, body, app_headers, profile
) -> None:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_deck_service] = lambda: AsyncMock(spec=DeckService)
    app.dependency_overrides[get_card_service] = lambda: AsyncMock(spec=CardService)
    app.dependency_overrides[get_library_service] = lambda: AsyncMock(
        spec=LibraryService
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        missing_key = await client.request(
            method, path, headers={"X-VK-User-ID": "12345678"}, json=body
        )
        assert missing_key.status_code == 401
        missing_vk = await client.request(
            method,
            path,
            headers=app_headers,
            params={"vk_user_id": "12345678"},
            json=body,
        )
        assert missing_vk.status_code == 422
        assert any(
            error["loc"] == ["header", "X-VK-User-ID"]
            for error in missing_vk.json()["detail"]
        )
    users.get_current.assert_not_awaited()


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": 2**31},
        {"limit": 0},
        {"limit": 101},
        {"grade": 12},
        {"subject": "invalid"},
        {"exam_type": "invalid"},
        {"search": "bad\x00search"},
    ],
)
async def test_catalog_rejects_invalid_filters(params, user_headers, profile) -> None:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    decks = AsyncMock(spec=DeckService)
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_deck_service] = lambda: decks
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/decks", headers=user_headers, params=params
        )
    assert response.status_code == 422
    decks.list_catalog.assert_not_awaited()


async def test_catalog_and_library_map_normalized_query_filters(
    user_headers, profile
) -> None:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    decks = AsyncMock(spec=DeckService)
    decks.list_catalog.return_value = DeckCatalogOutput(items=[], total=0)
    library = AsyncMock(spec=LibraryService)
    library.list_decks.return_value = LibraryListOutput(items=[], total=0)
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_deck_service] = lambda: decks
    app.dependency_overrides[get_library_service] = lambda: library
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/decks",
            headers=user_headers,
            params={
                "search": "  Test  ",
                "grade": 9,
                "page": 2,
                "limit": 10,
            },
        )
        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0}
        response = await client.get(
            "/api/v1/library/decks",
            headers=user_headers,
            params={"search": "   ", "subject": "physics", "page": 2, "limit": 10},
        )
        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0}
    query = decks.list_catalog.await_args.args[0]
    assert query.search == "Test" and query.grade == 9
    assert query.page == 2 and query.limit == 10
    library.list_decks.assert_awaited_once_with(
        profile.id, LibraryListInput(search=None, subject="physics", page=2, limit=10)
    )
    assert users.get_current.await_count == 2


async def test_share_preview_uses_router_user_check(user_headers, profile) -> None:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    decks = AsyncMock(spec=DeckService)
    decks.preview_by_share_code.return_value = DeckSharePreviewOutput(
        deck=DeckOutput(
            id=42,
            author_id=profile.id,
            title="Private deck",
            description=None,
            subject="physics",
            grade=None,
            exam_type=None,
            cover_color="gradient-blue",
            is_public=False,
            is_official=False,
            share_code="Abc123_-",
            cards_count=0,
            created_at=datetime(2026, 10, 23, tzinfo=UTC),
            updated_at=datetime(2026, 10, 23, tzinfo=UTC),
        ),
        cards=[],
    )
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_deck_service] = lambda: decks
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/decks/share/Abc123_-", headers=user_headers
        )
    assert response.status_code == 200
    assert response.json()["deck"]["id"] == 42
    assert response.json()["cards"] == []
    users.get_current.assert_awaited_once_with(profile.vk_user_id)
    decks.preview_by_share_code.assert_awaited_once_with("Abc123_-")


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (UnauthorizedError("Synchronize the user first."), 401),
        (ForbiddenError("User is disabled."), 403),
    ],
)
@pytest.mark.parametrize(
    "path", ["/api/v1/decks", "/api/v1/decks/share/Abc123_-", "/api/v1/library/decks"]
)
async def test_router_user_check_blocks_unknown_and_disabled_users(
    path, error, expected_status, user_headers
) -> None:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.side_effect = error
    decks = AsyncMock(spec=DeckService)
    library = AsyncMock(spec=LibraryService)
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_deck_service] = lambda: decks
    app.dependency_overrides[get_library_service] = lambda: library
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(path, headers=user_headers)
    assert response.status_code == expected_status
    users.get_current.assert_awaited_once_with(12345678)
    decks.list_catalog.assert_not_awaited()
    decks.preview_by_share_code.assert_not_awaited()
    library.list_decks.assert_not_awaited()


def test_openapi_exposes_arbitrary_settings_and_new_routes(
    resolve_openapi_schema,
) -> None:
    schema = create_app().openapi()
    assert set(schema["paths"]["/api/v1/users/me/settings"]) == {"put"}
    request = schema["components"]["schemas"]["UserSettingsReplaceRequest"]
    assert "additionalProperties" in request
    assert request.get("properties", {}) == {}
    update = schema["components"]["schemas"]["UserProfileUpdateRequest"]
    for field in ("first_name", "last_name", "timezone"):
        assert (
            resolve_openapi_schema(schema, update["properties"][field])["type"]
            == "string"
        )
        assert field not in update.get("required", [])
    avatar_types = {
        item["type"] for item in update["properties"]["avatar_url"]["anyOf"]
    }
    assert avatar_types == {"string", "null"}
    assert "avatar_url" not in update.get("required", [])
    new_limit = resolve_openapi_schema(
        schema, update["properties"]["daily_new_cards_limit"]
    )
    total_limit = resolve_openapi_schema(
        schema, update["properties"]["daily_total_cards_limit"]
    )
    assert (new_limit["type"], new_limit["minimum"], new_limit["maximum"]) == (
        "integer",
        1,
        250,
    )
    assert (total_limit["type"], total_limit["minimum"], total_limit["maximum"]) == (
        "integer",
        20,
        1000,
    )
    profile = schema["components"]["schemas"]["UserProfileResponse"]
    assert "additionalProperties" in profile["properties"]["settings"]
    assert "vibration_enabled" not in json.dumps(request)
