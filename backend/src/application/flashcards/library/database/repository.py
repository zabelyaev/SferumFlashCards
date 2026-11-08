from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from application.flashcards.decks.database.models import Deck
from application.flashcards.library.database.models import UserDeck

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ColumnElement

    from application.flashcards.library.contracts.inputs import LibraryListInput


class SQLALibraryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_membership(self, user_id: int, deck_id: int) -> UserDeck | None:
        return await self._session.scalar(
            select(UserDeck).where(
                UserDeck.user_id == user_id, UserDeck.deck_id == deck_id
            )
        )

    async def ensure_membership(self, *, user_id: int, deck_id: int) -> UserDeck:
        stmt = (
            insert(UserDeck)
            .values(user_id=user_id, deck_id=deck_id)
            .on_conflict_do_nothing(index_elements=[UserDeck.user_id, UserDeck.deck_id])
            .returning(UserDeck)
        )
        membership = await self._session.scalar(stmt)
        if membership is None:
            membership = await self.find_membership(user_id, deck_id)
        if membership is None:
            raise RuntimeError("Deck membership disappeared during insertion.")
        return membership

    async def remove_membership(self, *, user_id: int, deck_id: int) -> None:
        await self._session.execute(
            delete(UserDeck).where(
                UserDeck.user_id == user_id, UserDeck.deck_id == deck_id
            )
        )

    async def list_decks_for_user(
        self, user_id: int, data: LibraryListInput
    ) -> tuple[Sequence[Deck], int]:
        conditions: list[ColumnElement[bool]] = [UserDeck.user_id == user_id]
        if data.search is not None:
            conditions.append(Deck.title.icontains(data.search, autoescape=True))
        if data.subject is not None:
            conditions.append(Deck.subject == data.subject)
        total = await self._session.scalar(
            select(func.count())
            .select_from(UserDeck)
            .join(Deck, UserDeck.deck_id == Deck.id)
            .where(*conditions)
        )
        total = total or 0
        offset = (data.page - 1) * data.limit
        if offset >= total:
            return [], total
        stmt = (
            select(Deck)
            .join(UserDeck, UserDeck.deck_id == Deck.id)
            .where(*conditions)
            .order_by(UserDeck.created_at, UserDeck.id)
            .offset(offset)
            .limit(data.limit)
        )
        return (await self._session.scalars(stmt)).all(), total
