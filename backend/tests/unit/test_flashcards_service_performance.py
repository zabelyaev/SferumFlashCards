from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from application.flashcards.cards.contracts.inputs import (
    CardCreateInput,
    CardListInput,
    CardUpdateInput,
)
from application.flashcards.cards.contracts.mappers import to_card_output
from application.flashcards.cards.database.models import Card
from application.flashcards.cards.service import CardService
from application.flashcards.database.sqla_uow import SQLAFlashcardsUnitOfWork
from application.flashcards.decks.contracts.inputs import DeckUpdateInput
from application.flashcards.decks.contracts.mappers import to_deck_output
from application.flashcards.decks.database.models import Deck
from application.flashcards.decks.service import DeckService
from application.flashcards.library.database.models import UserDeck
from application.flashcards.library.service import LibraryService
from common.exceptions.forbidden import ForbiddenError

NOW = datetime(2026, 11, 6, tzinfo=UTC)


def sample_deck(**kwargs) -> Deck:
    values = {
        "id": 42,
        "author_id": 7,
        "title": "Private deck",
        "description": None,
        "subject": "physics",
        "grade": None,
        "exam_type": None,
        "cover_color": None,
        "is_public": False,
        "is_official": False,
        "share_code": "Abc123_-",
        "cards_count": 1,
        "created_at": NOW,
        "updated_at": NOW,
    }
    return Deck(**(values | kwargs))


def sample_card(card_id: int = 9) -> Card:
    return Card(
        id=card_id,
        deck_id=42,
        front=f"Question {card_id}",
        back="Answer",
        hint="Hint",
        explanation="Explanation",
        image_url="https://example.com/card.png",
        order_index=card_id,
        created_at=NOW,
        updated_at=NOW,
    )


def sample_membership() -> UserDeck:
    return UserDeck(id=3, user_id=7, deck_id=42, is_favorite=True, created_at=NOW)


def make_uow():
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    return uow


@pytest.mark.parametrize(
    ("author_id", "is_public", "is_member", "allowed", "queries_membership"),
    [
        (7, False, False, True, False),
        (8, True, False, True, False),
        (8, False, True, True, True),
        (8, False, False, False, True),
        (None, False, False, False, True),
    ],
)
async def test_library_add_shares_lock_preserves_rights_and_reuses_membership(
    author_id, is_public, is_member, allowed, queries_membership
) -> None:
    uow = make_uow()
    uow.decks.get_by_id.return_value = sample_deck(
        author_id=author_id, is_public=is_public
    )
    membership = sample_membership()
    uow.library.find_membership.return_value = membership if is_member else None
    uow.library.ensure_membership.return_value = membership
    service = LibraryService(lambda: uow)
    if allowed:
        result = await service.add(7, 42)
        assert result.model_dump() == {
            "id": 3,
            "user_id": 7,
            "deck_id": 42,
            "is_favorite": True,
            "created_at": NOW,
        }
        uow.commit.assert_awaited_once()
    else:
        with pytest.raises(ForbiddenError):
            await service.add(7, 42)
        uow.commit.assert_not_awaited()
    uow.decks.get_by_id.assert_awaited_once_with(42, for_share=True)
    if queries_membership:
        uow.library.find_membership.assert_awaited_once_with(7, 42)
    else:
        uow.library.find_membership.assert_not_awaited()
    if allowed and not is_member:
        uow.library.ensure_membership.assert_awaited_once_with(user_id=7, deck_id=42)
    else:
        uow.library.ensure_membership.assert_not_awaited()


async def test_add_by_share_code_keeps_private_access_and_uses_share_lock() -> None:
    uow = make_uow()
    uow.decks.get_by_share_code.return_value = sample_deck(author_id=8)
    uow.library.ensure_membership.return_value = sample_membership()
    result = await LibraryService(lambda: uow).add_by_share_code(7, "Abc123_-")
    assert result.id == 3
    uow.decks.get_by_share_code.assert_awaited_once_with("Abc123_-", for_share=True)
    uow.library.find_membership.assert_not_awaited()
    uow.library.ensure_membership.assert_awaited_once_with(user_id=7, deck_id=42)
    uow.commit.assert_awaited_once()


@pytest.mark.parametrize(
    ("method", "public", "repeated", "budget"),
    [
        ("add", False, True, 2),
        ("add", True, False, 2),
        ("add", True, True, 3),
        ("add_by_share_code", False, False, 2),
        ("add_by_share_code", False, True, 3),
    ],
)
async def test_library_add_sql_budget(method, public, repeated, budget) -> None:
    session = AsyncMock(spec=AsyncSession)
    deck = sample_deck(author_id=8, is_public=public)
    membership = sample_membership()
    private_repeat = method == "add" and not public
    session.scalar.side_effect = (
        [deck, membership]
        if private_repeat or not repeated
        else [deck, None, membership]
    )
    service = LibraryService(
        lambda: SQLAFlashcardsUnitOfWork(MagicMock(return_value=session))
    )
    result = await getattr(service, method)(7, 42 if method == "add" else "Abc123_-")
    assert result.id == membership.id
    assert session.scalar.await_count == budget
    session.scalars.assert_not_awaited()
    session.execute.assert_not_awaited()
    statements = [
        str(call.args[0].compile(dialect=postgresql.dialect()))
        for call in session.scalar.await_args_list
    ]
    assert statements[0].endswith("FOR SHARE OF decks")
    inserts = [sql for sql in statements if sql.startswith("INSERT")]
    assert len(inserts) == (0 if private_repeat else 1)
    if inserts:
        assert "ON CONFLICT (user_id, deck_id) DO NOTHING" in inserts[0]


@pytest.mark.parametrize(
    ("author_id", "is_public", "member"),
    [(7, False, False), (8, True, False), (8, False, True)],
)
@pytest.mark.parametrize("total", [0, 25])
async def test_cards_share_lock_then_authorize_and_use_cached_total(
    author_id, is_public, member, total
) -> None:
    uow = make_uow()
    uow.decks.get_by_id.return_value = sample_deck(
        author_id=author_id, is_public=is_public, cards_count=total
    )
    uow.library.find_membership.return_value = sample_membership() if member else None
    uow.cards.list_page_for_deck.return_value = ([], total)
    model = CardListInput(page=99)
    result = await CardService(lambda: uow).list_for_deck(7, 42, model)
    assert result.total == total
    assert result.items == []
    uow.decks.get_by_id.assert_awaited_once_with(42, for_share=True)
    uow.cards.list_page_for_deck.assert_awaited_once_with(42, model, total=total)
    assert uow.library.find_membership.await_count == int(member)
    uow.commit.assert_not_awaited()


@pytest.mark.parametrize("member", [False, True])
@pytest.mark.parametrize("page", [1, 99])
async def test_cards_service_sql_budget_without_count(member, page) -> None:
    session = AsyncMock(spec=AsyncSession)
    deck = sample_deck(author_id=8 if member else 7)
    session.scalar.side_effect = [deck, sample_membership()] if member else [deck]
    session.scalars.return_value = MagicMock()
    session.scalars.return_value.all.return_value = [sample_card()]
    service = CardService(
        lambda: SQLAFlashcardsUnitOfWork(MagicMock(return_value=session))
    )
    result = await service.list_for_deck(7, 42, CardListInput(page=page))
    assert result.total == 1
    assert len(result.items) == (1 if page == 1 else 0)
    assert session.scalar.await_count == 1 + int(member)
    assert session.scalars.await_count == int(page == 1)
    session.execute.assert_not_awaited()
    for call in session.scalar.await_args_list + session.scalars.await_args_list:
        assert "count(" not in str(call.args[0]).lower()


@pytest.mark.parametrize(
    "operation", ["deck_update", "deck_delete", "create", "update", "delete", "remove"]
)
async def test_content_mutations_and_library_remove_keep_exclusive_lock(
    operation,
) -> None:
    uow = make_uow()
    uow.decks.get_by_id.return_value = sample_deck()
    uow.cards.append.return_value = sample_card()
    uow.cards.get_by_id.return_value = sample_card()
    cards = CardService(lambda: uow)
    decks = DeckService(lambda: uow)
    if operation == "deck_update":
        await decks.update(7, 42, DeckUpdateInput(title="Changed"))
    elif operation == "deck_delete":
        await decks.delete(7, 42)
    elif operation == "create":
        await cards.create(7, 42, CardCreateInput(front="Q", back="A"))
    elif operation == "update":
        await cards.update(7, 42, 9, CardUpdateInput(front="Changed"))
    elif operation == "delete":
        await cards.delete(7, 42, 9)
    else:
        await LibraryService(lambda: uow).remove(7, 42)
    uow.decks.get_by_id.assert_awaited_once_with(42, for_update=True)
    uow.commit.assert_awaited_once()


@pytest.mark.parametrize("count", [0, 125])
async def test_full_share_preview_count_comes_from_returned_cards_without_lock(
    count,
) -> None:
    uow = make_uow()
    deck = sample_deck(cards_count=77)
    cards = [sample_card(card_id) for card_id in range(1, count + 1)]
    uow.decks.get_by_share_code.return_value = deck
    uow.cards.list_for_deck.return_value = cards
    result = await DeckService(lambda: uow).preview_by_share_code("Abc123_-")
    assert result.model_dump() == {
        "deck": to_deck_output(deck).model_dump() | {"cards_count": count},
        "cards": [to_card_output(card).model_dump() for card in cards],
    }
    assert deck.cards_count == 77
    uow.decks.get_by_share_code.assert_awaited_once_with("Abc123_-")
    uow.cards.list_for_deck.assert_awaited_once_with(42)
    uow.cards.list_page_for_deck.assert_not_awaited()
    uow.flush.assert_not_awaited()
    uow.commit.assert_not_awaited()


async def test_full_share_preview_sql_budget_is_two_unlocked_selects() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = sample_deck(cards_count=77)
    session.scalars.return_value = MagicMock()
    session.scalars.return_value.all.return_value = [sample_card()]
    service = DeckService(
        lambda: SQLAFlashcardsUnitOfWork(MagicMock(return_value=session))
    )
    result = await service.preview_by_share_code("Abc123_-")
    assert result.deck.cards_count == len(result.cards) == 1
    session.scalar.assert_awaited_once()
    session.scalars.assert_awaited_once()
    session.execute.assert_not_awaited()
    session.flush.assert_not_awaited()
    session.commit.assert_not_awaited()
    for call in session.scalar.await_args_list + session.scalars.await_args_list:
        sql = str(call.args[0].compile(dialect=postgresql.dialect()))
        assert sql.startswith("SELECT")
        assert "FOR " not in sql
        assert "count(" not in sql.lower()
