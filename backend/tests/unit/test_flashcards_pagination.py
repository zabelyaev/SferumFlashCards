from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from api.dependencies.services import (
    get_card_service,
    get_library_service,
    get_user_service,
)
from application.accounts.users.service import UserService
from application.flashcards.cards.contracts.inputs import CardListInput
from application.flashcards.cards.contracts.outputs import (
    CardListOutput,
    CardOutput,
)
from application.flashcards.cards.service import CardService
from application.flashcards.decks.contracts.outputs import DeckOutput
from application.flashcards.decks.database.models import Deck
from application.flashcards.library.contracts.inputs import LibraryListInput
from application.flashcards.library.contracts.outputs import LibraryListOutput
from application.flashcards.library.service import LibraryService
from common.exceptions.forbidden import ForbiddenError
from common.exceptions.not_found import NotFoundError
from main import create_app


def sample_deck() -> DeckOutput:
    timestamp = datetime(2026, 10, 23, tzinfo=UTC)
    return DeckOutput(
        id=42,
        author_id=7,
        title="Private deck",
        description=None,
        subject="physics",
        grade=None,
        exam_type=None,
        cover_color="gradient-blue",
        is_public=False,
        is_official=False,
        share_code="Abc123_-",
        cards_count=1,
        created_at=timestamp,
        updated_at=timestamp,
    )


def sample_card() -> CardOutput:
    timestamp = datetime(2026, 10, 23, tzinfo=UTC)
    return CardOutput(
        id=9,
        deck_id=42,
        front="Question",
        back="Answer",
        hint=None,
        explanation=None,
        image_url=None,
        order_index=3,
        created_at=timestamp,
        updated_at=timestamp,
    )


@pytest.mark.parametrize(
    ("params", "page", "limit"),
    [
        ({}, 1, 20),
        ({"page": 2, "limit": 3}, 2, 3),
        ({"page": 2**31 - 1, "limit": 100}, 2**31 - 1, 100),
    ],
)
async def test_library_page_passes_filters_and_returns_total(
    params, page, limit, user_headers, profile
) -> None:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    library = AsyncMock(spec=LibraryService)
    library.list_decks.return_value = LibraryListOutput(items=[sample_deck()], total=7)
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_library_service] = lambda: library
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/library/decks",
            headers=user_headers,
            params={**params, "search": "  private  ", "subject": "physics"},
        )
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"items", "total"}
    assert data["total"] == 7
    assert [deck["id"] for deck in data["items"]] == [42]
    assert data["items"][0]["is_public"] is False
    library.list_decks.assert_awaited_once_with(
        profile.id,
        LibraryListInput(search="private", subject="physics", page=page, limit=limit),
    )


@pytest.mark.parametrize(
    ("params", "page", "limit"),
    [
        ({}, 1, 20),
        ({"page": 2, "limit": 3}, 2, 3),
        ({"page": 2**31 - 1, "limit": 100}, 2**31 - 1, 100),
    ],
)
async def test_cards_page_passes_pagination_and_returns_total(
    params, page, limit, user_headers, profile
) -> None:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    cards = AsyncMock(spec=CardService)
    cards.list_for_deck.return_value = CardListOutput(items=[sample_card()], total=7)
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_card_service] = lambda: cards
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/decks/42/cards", headers=user_headers, params=params
        )
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"items", "total"}
    assert data["total"] == 7
    assert [card["id"] for card in data["items"]] == [9]
    assert data["items"][0]["deck_id"] == 42
    cards.list_for_deck.assert_awaited_once_with(
        profile.id, 42, CardListInput(page=page, limit=limit)
    )


@pytest.mark.parametrize("path", ["/api/v1/library/decks", "/api/v1/decks/42/cards"])
@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": -1},
        {"page": 2**31},
        {"page": "abc"},
        {"page": "1.5"},
        {"limit": 0},
        {"limit": -1},
        {"limit": 101},
        {"limit": "abc"},
        {"limit": "1.5"},
    ],
)
async def test_invalid_pagination_is_rejected_before_listing(
    path, params, user_headers, profile
) -> None:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    cards = AsyncMock(spec=CardService)
    library = AsyncMock(spec=LibraryService)
    app.dependency_overrides[get_user_service] = lambda: users
    app.dependency_overrides[get_card_service] = lambda: cards
    app.dependency_overrides[get_library_service] = lambda: library
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(path, headers=user_headers, params=params)
    assert response.status_code == 422
    assert any(
        error["loc"] == ["query", next(iter(params))]
        for error in response.json()["detail"]
    )
    cards.list_for_deck.assert_not_awaited()
    library.list_decks.assert_not_awaited()


@pytest.mark.parametrize("schema", [CardListInput, LibraryListInput])
@pytest.mark.parametrize(
    "params",
    [{"page": 0}, {"page": 2**31}, {"limit": 0}, {"limit": 101}, {"page": True}],
)
def test_application_pagination_validates_limits(schema, params) -> None:
    with pytest.raises(ValidationError):
        schema(**params)


@pytest.mark.parametrize("schema", [CardListOutput, LibraryListOutput])
def test_application_page_rejects_negative_total(schema) -> None:
    with pytest.raises(ValidationError):
        schema(items=[], total=-1)


@pytest.mark.parametrize("missing", [False, True])
async def test_cards_check_access_before_loading_page(missing) -> None:
    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.decks.get_by_id = AsyncMock()
    uow.cards.list_page_for_deck = AsyncMock()
    uow.library.find_membership = AsyncMock(return_value=None)
    if missing:
        uow.decks.get_by_id.side_effect = NotFoundError("Deck not found.")
    else:
        uow.decks.get_by_id.return_value = Deck(id=42, author_id=10, is_public=False)
    service = CardService(lambda: uow)
    with pytest.raises(NotFoundError if missing else ForbiddenError):
        await service.list_for_deck(7, 42, CardListInput(page=99, limit=1))
    uow.cards.list_page_for_deck.assert_not_awaited()
