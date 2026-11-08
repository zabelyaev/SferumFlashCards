from typing import TYPE_CHECKING

from sqlalchemy import func, select

from application.flashcards.cards.database.models import Card
from common.exceptions.not_found import NotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from application.flashcards.cards.contracts.inputs import (
        CardCreateInput,
        CardListInput,
        CardUpdateInput,
    )


class SQLACardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_deck(self, deck_id: int) -> Sequence[Card]:
        return (
            await self._session.scalars(
                select(Card)
                .where(Card.deck_id == deck_id)
                .order_by(Card.order_index, Card.id)
            )
        ).all()

    async def list_page_for_deck(
        self, deck_id: int, data: CardListInput, *, total: int
    ) -> tuple[Sequence[Card], int]:

        offset = (data.page - 1) * data.limit
        if offset >= total:
            return [], total
        stmt = (
            select(Card)
            .where(Card.deck_id == deck_id)
            .order_by(Card.order_index, Card.id)
            .offset(offset)
            .limit(data.limit)
        )
        return (await self._session.scalars(stmt)).all(), total

    async def get_by_id(self, card_id: int, *, deck_id: int) -> Card:
        card = await self._session.scalar(
            select(Card).where(Card.deck_id == deck_id, Card.id == card_id)
        )
        if card is None:
            raise NotFoundError("Card not found.")
        return card

    async def append(self, *, deck_id: int, data: CardCreateInput) -> Card:
        max_index = await self._session.scalar(
            select(func.max(Card.order_index)).where(Card.deck_id == deck_id)
        )
        card = Card(
            deck_id=deck_id,
            front=data.front,
            back=data.back,
            hint=data.hint,
            explanation=data.explanation,
            image_url=str(data.image_url) if data.image_url is not None else None,
            order_index=0 if max_index is None else max_index + 1,
        )
        self._session.add(card)
        await self._session.flush()
        return card

    async def delete(self, card: Card) -> None:
        await self._session.delete(card)

    async def update(self, card: Card, data: CardUpdateInput) -> None:
        for field, value in data.model_dump(mode="json", exclude_unset=True).items():
            setattr(card, field, value)
