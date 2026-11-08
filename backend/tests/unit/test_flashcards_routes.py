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
from api.v1.flashcards.cards.contracts.mappers import to_card_input, to_card_response
from api.v1.flashcards.cards.contracts.requests import CardCreateRequest
from api.v1.flashcards.decks.contracts.mappers import to_deck_input
from api.v1.flashcards.decks.contracts.requests import DeckCreateRequest
from application.accounts.users.service import UserService
from application.flashcards.cards.contracts.inputs import CardCreateInput
from application.flashcards.cards.contracts.outputs import (
    CardOutput as ApplicationCardOutput,
)
from application.flashcards.cards.service import CardService
from application.flashcards.decks.contracts.inputs import DeckCreateInput
from application.flashcards.decks.service import DeckService
from application.flashcards.library.contracts.inputs import LibraryListInput
from application.flashcards.library.contracts.outputs import (
    LibraryListOutput,
    UserDeckOutput,
)
from application.flashcards.library.service import LibraryService
from main import create_app


def test_independent_schemas_and_mappers() -> None:
    deck = DeckCreateRequest(title=" title ", subject="physics")
    mapped = to_deck_input(deck)
    assert type(mapped) is DeckCreateInput
    assert mapped.title == "title"
    assert not issubclass(DeckCreateRequest, DeckCreateInput)
    card = to_card_input(CardCreateRequest(front=" a ", back=" b "))
    assert type(card) is CardCreateInput
    assert card.front == "a"
    with pytest.raises(ValidationError):
        CardCreateRequest(front=" ", back="answer")
    with pytest.raises(ValidationError):
        DeckCreateRequest(title="x", subject="physics", author_id=999)
    with pytest.raises(ValidationError):
        CardCreateRequest(front="x", back="y", order_index=42)
    with pytest.raises(ValidationError):
        CardCreateInput(front="x", back="y", order_index=42)


def test_card_response_mapper_does_not_export_internal_fields() -> None:
    from datetime import UTC, datetime

    class InternalCard(ApplicationCardOutput):
        internal_note: str = "private"

    timestamp = datetime(2026, 10, 23, tzinfo=UTC)
    source = InternalCard(
        id=1,
        deck_id=2,
        front="question",
        back="answer",
        hint=None,
        explanation=None,
        image_url=None,
        order_index=0,
        created_at=timestamp,
        updated_at=timestamp,
    )
    assert "internal_note" not in to_card_response(source).model_dump()


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/v1/decks", {"title": "x", "subject": "physics"}),
        ("GET", "/api/v1/decks/1", None),
        ("DELETE", "/api/v1/decks/1", None),
        ("POST", "/api/v1/decks/1/cards", {"front": "x", "back": "y"}),
        ("GET", "/api/v1/decks/1/cards", None),
        ("DELETE", "/api/v1/decks/1/cards/2", None),
        ("GET", "/api/v1/library/decks", None),
        ("PUT", "/api/v1/library/decks/1", None),
        ("DELETE", "/api/v1/library/decks/1", None),
    ],
)
async def test_registered_routes_require_every_key_and_vk_id(
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
        for key in app_headers:
            headers = {
                **{k: v for k, v in app_headers.items() if k != key},
                "X-VK-User-ID": "12345678",
            }
            response = await client.request(
                method,
                path,
                headers=headers,
                json=body,
            )
            assert response.status_code == 401
        response = await client.request(method, path, headers=app_headers, json=body)
        assert response.status_code == 422
    assert (
        path.replace("/1", "/{deck_id}").replace("/2", "/{card_id}")
        in app.openapi()["paths"]
    )


async def test_library_routes_use_library_prefix_and_preserve_methods(
    user_headers, profile
) -> None:
    from datetime import UTC, datetime

    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    service = AsyncMock(spec=LibraryService)
    service.list_decks.return_value = LibraryListOutput(items=[], total=0)
    service.add.return_value = UserDeckOutput(
        id=9,
        user_id=profile.id,
        deck_id=42,
        is_favorite=False,
        created_at=datetime(2026, 10, 23, tzinfo=UTC),
    )
    service.add_by_share_code.return_value = service.add.return_value
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_library_service] = lambda: service
    obsolete_prefixes = ("/api/v1/users/me/decks", "/api/v1/me/decks")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=user_headers
    ) as client:
        response = await client.get("/api/v1/library/decks")
        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0}
        response = await client.put("/api/v1/library/decks/42")
        assert response.status_code == 200
        assert response.json()["deck_id"] == 42
        response = await client.put("/api/v1/library/decks/share/Abc123_-")
        assert response.status_code == 200
        assert response.json()["deck_id"] == 42
        response = await client.delete("/api/v1/library/decks/42")
        assert response.status_code == 204
        for prefix in obsolete_prefixes:
            for method, path in (
                ("GET", prefix),
                ("PUT", prefix + "/42"),
                ("DELETE", prefix + "/42"),
                ("PUT", prefix + "/share/Abc123_-"),
            ):
                assert (await client.request(method, path)).status_code == 404

    service.list_decks.assert_awaited_once_with(profile.id, LibraryListInput())
    service.add.assert_awaited_once_with(profile.id, 42)
    service.add_by_share_code.assert_awaited_once_with(profile.id, "Abc123_-")
    service.remove.assert_awaited_once_with(profile.id, 42)
    paths = app.openapi()["paths"]
    assert set(paths["/api/v1/library/decks"]) == {"get"}
    assert set(paths["/api/v1/library/decks/{deck_id}"]) == {"put", "delete"}
    assert set(paths["/api/v1/library/decks/share/{share_code}"]) == {"put"}
    for prefix in obsolete_prefixes:
        assert prefix not in paths
        assert prefix + "/{deck_id}" not in paths
        assert prefix + "/share/{share_code}" not in paths


@pytest.mark.parametrize(
    ("path", "service_name", "service_method", "ids"),
    [
        ("/api/v1/decks/42", "decks", "delete", (42,)),
        ("/api/v1/decks/42/cards/9", "cards", "delete", (42, 9)),
        ("/api/v1/library/decks/42", "library", "remove", (42,)),
    ],
)
async def test_router_and_handler_reuse_current_user_once(
    path, service_name, service_method, ids, user_headers, profile
) -> None:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    services = {
        "decks": AsyncMock(spec=DeckService),
        "cards": AsyncMock(spec=CardService),
        "library": AsyncMock(spec=LibraryService),
    }
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_deck_service] = lambda: services["decks"]
    app.dependency_overrides[get_card_service] = lambda: services["cards"]
    app.dependency_overrides[get_library_service] = lambda: services["library"]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.delete(path, headers=user_headers)
    assert response.status_code == 204
    users.get_current.assert_awaited_once_with(profile.vk_user_id)
    getattr(services[service_name], service_method).assert_awaited_once_with(
        profile.id, *ids
    )


@pytest.mark.parametrize(
    "deck_id", ["0", "-1", "abc", "1.5", "1e0", "9223372036854775808"]
)
async def test_deck_path_rejects_invalid_ids(deck_id, user_headers, profile) -> None:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    decks = AsyncMock(spec=DeckService)
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_deck_service] = lambda: decks
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.delete(
            f"/api/v1/decks/{deck_id}",
            headers=user_headers,
        )
    assert response.status_code == 422
    decks.delete.assert_not_awaited()


@pytest.mark.parametrize(
    ("deck_id", "expected"),
    [("1", 1), ("01", 1), ("+1", 1), ("1.0", 1), ("9223372036854775807", 2**63 - 1)],
)
async def test_deck_path_parses_bigint_as_an_integer(
    user_headers, profile, deck_id, expected
) -> None:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    decks = AsyncMock(spec=DeckService)
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_deck_service] = lambda: decks
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.delete(
            f"/api/v1/decks/{deck_id}",
            headers=user_headers,
        )
    assert response.status_code == 204
    users.get_current.assert_awaited_once_with(profile.vk_user_id)
    decks.delete.assert_awaited_once_with(profile.id, expected)
