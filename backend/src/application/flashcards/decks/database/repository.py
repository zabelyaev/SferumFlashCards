from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from application.flashcards.decks.database.models import Deck, generate_share_code
from common.exceptions.not_found import NotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ColumnElement

    from application.flashcards.decks.contracts.inputs import (
        DeckCatalogInput,
        DeckCreateInput,
        DeckUpdateInput,
    )


class SQLADeckRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self, deck_id: int, *, for_update: bool = False, for_share: bool = False
    ) -> Deck:
        if for_update and for_share:
            raise ValueError("Deck lock modes are mutually exclusive.")
        stmt = select(Deck).where(Deck.id == deck_id)
        if for_update or for_share:
            stmt = stmt.with_for_update(read=for_share, of=Deck)
        deck = await self._session.scalar(stmt)
        if deck is None:
            raise NotFoundError("Deck not found.")
        return deck

    async def get_by_share_code(
        self, share_code: str, *, for_update: bool = False, for_share: bool = False
    ) -> Deck:
        if for_update and for_share:
            raise ValueError("Deck lock modes are mutually exclusive.")
        stmt = select(Deck).where(Deck.share_code == share_code)
        if for_update or for_share:
            stmt = stmt.with_for_update(read=for_share, of=Deck)
        deck = await self._session.scalar(stmt)
        if deck is None:
            raise NotFoundError("Deck not found.")
        return deck

    async def list_catalog(self, data: DeckCatalogInput) -> tuple[Sequence[Deck], int]:
        conditions: list[ColumnElement[bool]] = [Deck.is_public.is_(True)]
        if data.search is not None:
            conditions.append(Deck.title.icontains(data.search, autoescape=True))
        if data.subject is not None:
            conditions.append(Deck.subject == data.subject)
        if data.grade is not None:
            conditions.append(Deck.grade == data.grade)
        if data.exam_type is not None:
            conditions.append(Deck.exam_type == data.exam_type)
        total = await self._session.scalar(
            select(func.count()).select_from(Deck).where(*conditions)
        )
        total = total or 0
        offset = (data.page - 1) * data.limit
        if offset >= total:
            return [], total
        stmt = (
            select(Deck)
            .where(*conditions)
            .order_by(Deck.created_at.desc(), Deck.id.desc())
            .offset(offset)
            .limit(data.limit)
        )
        return (await self._session.scalars(stmt)).all(), total

    async def create(self, *, author_id: int, data: DeckCreateInput) -> Deck:
        for _ in range(5):
            stmt = (
                insert(Deck)
                .values(
                    author_id=author_id,
                    title=data.title,
                    description=data.description,
                    subject=data.subject,
                    grade=data.grade,
                    exam_type=data.exam_type,
                    cover_color=data.cover_color,
                    is_public=data.is_public,
                    share_code=generate_share_code(),
                )
                .on_conflict_do_nothing(index_elements=[Deck.share_code])
                .returning(Deck)
            )
            deck = await self._session.scalar(stmt)
            if deck is not None:
                return deck
        raise RuntimeError("Unable to generate a unique deck share code.")

    async def delete(self, deck: Deck) -> None:
        await self._session.delete(deck)

    async def update(self, deck: Deck, data: DeckUpdateInput) -> None:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(deck, field, value)
