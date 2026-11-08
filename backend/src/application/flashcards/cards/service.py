from __future__ import annotations

from typing import TYPE_CHECKING

from application.flashcards.cards.contracts.mappers import (
    to_card_list_output,
    to_card_output,
)
from application.flashcards.shared.access import require_readable_deck
from application.flashcards.shared.policies import require_author

if TYPE_CHECKING:
    from application.flashcards.cards.contracts.inputs import (
        CardCreateInput,
        CardListInput,
        CardUpdateInput,
    )
    from application.flashcards.cards.contracts.outputs import (
        CardListOutput,
        CardOutput,
    )
    from application.flashcards.database.uow import FlashcardsUnitOfWorkFactory


class CardService:
    def __init__(self, uow_factory: FlashcardsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def list_for_deck(
        self, user_id: int, deck_id: int, model: CardListInput
    ) -> CardListOutput:
        async with self._uow_factory() as uow:
            deck = await uow.decks.get_by_id(deck_id, for_share=True)
            await require_readable_deck(deck, user_id, uow.library)
            cards, total = await uow.cards.list_page_for_deck(
                deck_id, model, total=deck.cards_count
            )
            return to_card_list_output(cards, total)

    async def create(
        self, user_id: int, deck_id: int, model: CardCreateInput
    ) -> CardOutput:
        async with self._uow_factory() as uow:
            deck = await uow.decks.get_by_id(deck_id, for_update=True)
            require_author(deck, user_id)

            card = await uow.cards.append(deck_id=deck.id, data=model)
            deck.cards_count += 1

            await uow.flush()
            result = to_card_output(card)
            await uow.commit()
        return result

    async def delete(self, user_id: int, deck_id: int, card_id: int) -> None:
        async with self._uow_factory() as uow:
            deck = await uow.decks.get_by_id(deck_id, for_update=True)
            require_author(deck, user_id)
            card = await uow.cards.get_by_id(card_id, deck_id=deck_id)
            await uow.cards.delete(card)
            deck.cards_count -= 1
            await uow.commit()

    async def update(
        self, user_id: int, deck_id: int, card_id: int, model: CardUpdateInput
    ) -> CardOutput:
        async with self._uow_factory() as uow:
            deck = await uow.decks.get_by_id(deck_id, for_update=True)
            require_author(deck, user_id)
            card = await uow.cards.get_by_id(card_id, deck_id=deck_id)
            await uow.cards.update(card, model)
            await uow.flush()
            result = to_card_output(card)
            await uow.commit()
        return result
