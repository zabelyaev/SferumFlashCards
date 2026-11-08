from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from application.flashcards.cards.contracts.inputs import CardListInput
from application.flashcards.cards.database.models import Card
from application.flashcards.cards.database.repository import SQLACardRepository
from application.flashcards.decks.contracts.inputs import DeckCatalogInput
from application.flashcards.decks.database.models import Deck
from application.flashcards.decks.database.repository import SQLADeckRepository
from application.flashcards.library.contracts.inputs import LibraryListInput
from application.flashcards.library.database.repository import SQLALibraryRepository
from common.exceptions.not_found import NotFoundError


def compile_sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


@pytest.mark.parametrize(
    ("method", "value", "predicate"),
    [
        ("get_by_id", 42, "decks.id = 42"),
        ("get_by_share_code", "Abc123_-", "decks.share_code = 'Abc123_-'"),
    ],
)
@pytest.mark.parametrize(
    ("options", "lock"),
    [
        ({}, None),
        ({"for_update": True}, "FOR UPDATE OF decks"),
        ({"for_share": True}, "FOR SHARE OF decks"),
    ],
)
async def test_deck_lookup_selects_only_deck_with_explicit_lock(
    method, value, predicate, options, lock
) -> None:
    session = AsyncMock(spec=AsyncSession)
    deck = Deck(id=42)
    session.scalar.return_value = deck
    result = await getattr(SQLADeckRepository(session), method)(value, **options)
    assert result is deck
    session.scalar.assert_awaited_once()
    session.scalars.assert_not_awaited()
    statement = session.scalar.await_args.args[0]
    assert list(statement.selected_columns) == list(Deck.__table__.columns)
    sql = compile_sql(statement)
    assert predicate in sql
    assert "JOIN" not in sql
    if lock is None:
        assert "FOR " not in sql
    else:
        assert sql.endswith(lock)


@pytest.mark.parametrize("method", ["get_by_id", "get_by_share_code"])
async def test_deck_lookup_rejects_conflicting_lock_modes(method) -> None:
    session = AsyncMock(spec=AsyncSession)
    with pytest.raises(ValueError, match="mutually exclusive"):
        await getattr(SQLADeckRepository(session), method)(
            42 if method == "get_by_id" else "Abc123_-",
            for_update=True,
            for_share=True,
        )
    session.scalar.assert_not_awaited()


@pytest.mark.parametrize("method", ["get_by_id", "get_by_share_code"])
async def test_shared_deck_lookup_preserves_not_found(method) -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None
    with pytest.raises(NotFoundError, match="Deck not found"):
        await getattr(SQLADeckRepository(session), method)(
            42 if method == "get_by_id" else "Abc123_-", for_share=True
        )
    session.scalar.assert_awaited_once()


@pytest.mark.parametrize(
    ("total", "page", "limit"),
    [(0, 1, 20), (20, 2, 20), (3, 2**31 - 1, 100)],
)
async def test_card_page_beyond_total_uses_no_sql(total, page, limit) -> None:
    session = AsyncMock(spec=AsyncSession)
    result = await SQLACardRepository(session).list_page_for_deck(
        42, CardListInput(page=page, limit=limit), total=total
    )
    assert result == ([], total)
    session.scalar.assert_not_awaited()
    session.scalars.assert_not_awaited()
    session.execute.assert_not_awaited()


async def test_card_page_selects_only_card_columns_without_count_query() -> None:
    session = AsyncMock(spec=AsyncSession)
    cards = [Card(id=9, deck_id=42)]
    session.scalars.return_value = MagicMock()
    session.scalars.return_value.all.return_value = cards
    result = await SQLACardRepository(session).list_page_for_deck(
        42, CardListInput(page=2, limit=3), total=7
    )
    assert result == (cards, 7)
    session.scalar.assert_not_awaited()
    session.scalars.assert_awaited_once()
    statement = session.scalars.await_args.args[0]
    assert list(statement.selected_columns) == list(Card.__table__.columns)
    sql = compile_sql(statement)
    assert "WHERE cards.deck_id = 42" in sql
    assert "ORDER BY cards.order_index, cards.id" in sql
    assert "LIMIT 3 OFFSET 3" in sql
    assert "count(" not in sql.lower()
    assert "JOIN" not in sql


async def test_full_preview_selects_all_card_columns_without_limit_or_lock() -> None:
    session = AsyncMock(spec=AsyncSession)
    cards = [Card(id=card_id, deck_id=42) for card_id in range(125)]
    session.scalars.return_value = MagicMock()
    session.scalars.return_value.all.return_value = cards
    assert await SQLACardRepository(session).list_for_deck(42) == cards
    session.scalar.assert_not_awaited()
    session.scalars.assert_awaited_once()
    statement = session.scalars.await_args.args[0]
    assert list(statement.selected_columns) == list(Card.__table__.columns)
    sql = compile_sql(statement)
    assert "WHERE cards.deck_id = 42" in sql
    assert "ORDER BY cards.order_index, cards.id" in sql
    assert "LIMIT" not in sql
    assert "OFFSET" not in sql
    assert "FOR " not in sql
    assert "JOIN" not in sql


@pytest.mark.parametrize("kind", ["catalog", "library"])
@pytest.mark.parametrize(
    ("total", "page", "limit"),
    [(0, 1, 20), (20, 2, 20), (3, 2**31 - 1, 100)],
)
async def test_deck_page_beyond_total_only_counts(kind, total, page, limit) -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = total
    if kind == "catalog":
        result = await SQLADeckRepository(session).list_catalog(
            DeckCatalogInput(page=page, limit=limit)
        )
    else:
        result = await SQLALibraryRepository(session).list_decks_for_user(
            7, LibraryListInput(page=page, limit=limit)
        )
    assert result == ([], total)
    session.scalar.assert_awaited_once()
    session.scalars.assert_not_awaited()
    statement = session.scalar.await_args.args[0]
    assert len(statement.selected_columns) == 1
    assert "SELECT count(*)" in compile_sql(statement)


@pytest.mark.parametrize("kind", ["catalog", "library"])
async def test_deck_page_preserves_projection_filters_and_stable_order(kind) -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = 7
    decks = [Deck(id=42)]
    session.scalars.return_value = MagicMock()
    session.scalars.return_value.all.return_value = decks
    filters = {"search": "A%_", "subject": "physics", "page": 2, "limit": 3}
    if kind == "catalog":
        result = await SQLADeckRepository(session).list_catalog(
            DeckCatalogInput(**filters, grade=9, exam_type="oge")
        )
    else:
        result = await SQLALibraryRepository(session).list_decks_for_user(
            7, LibraryListInput(**filters)
        )
    assert result == (decks, 7)
    session.scalar.assert_awaited_once()
    session.scalars.assert_awaited_once()
    count = session.scalar.await_args.args[0]
    page = session.scalars.await_args.args[0]
    assert len(count.selected_columns) == 1
    assert list(page.selected_columns) == list(Deck.__table__.columns)
    count_sql, page_sql = compile_sql(count), compile_sql(page)
    for sql in (count_sql, page_sql):
        assert "decks.subject = 'physics'" in sql
        assert "A/%%/_" in sql
        assert "ESCAPE '/'" in sql
        if kind == "catalog":
            assert "decks.is_public IS true" in sql
            assert "decks.grade = 9" in sql
            assert "decks.exam_type = 'oge'" in sql
        else:
            assert "user_decks.user_id = 7" in sql
            assert "JOIN decks ON user_decks.deck_id = decks.id" in count_sql
            assert "JOIN user_decks ON user_decks.deck_id = decks.id" in page_sql
    assert "LIMIT 3 OFFSET 3" in page_sql
    assert (
        "ORDER BY decks.created_at DESC, decks.id DESC"
        if kind == "catalog"
        else "ORDER BY user_decks.created_at, user_decks.id"
    ) in page_sql
