from __future__ import annotations

from typing import TYPE_CHECKING

from application.flashcards.decks.contracts.mappers import (
    to_deck_catalog_output,
    to_deck_output,
    to_deck_share_preview_output,
)
from application.flashcards.shared.access import require_readable_deck
from application.flashcards.shared.policies import require_author

if TYPE_CHECKING:
    from application.flashcards.database.uow import FlashcardsUnitOfWorkFactory
    from application.flashcards.decks.contracts.inputs import (
        DeckCatalogInput,
        DeckCreateInput,
        DeckUpdateInput,
    )
    from application.flashcards.decks.contracts.outputs import (
        DeckCatalogOutput,
        DeckOutput,
        DeckSharePreviewOutput,
    )


class DeckService:
    def __init__(self, uow_factory: FlashcardsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def create(self, user_id: int, model: DeckCreateInput) -> DeckOutput:
        async with self._uow_factory() as uow:
            deck = await uow.decks.create(author_id=user_id, data=model)
            await uow.library.ensure_membership(user_id=user_id, deck_id=deck.id)
            await uow.flush()
            result = to_deck_output(deck)
            await uow.commit()
            return result

    async def get(self, user_id: int, deck_id: int) -> DeckOutput:
        async with self._uow_factory() as uow:
            deck = await uow.decks.get_by_id(deck_id)
            await require_readable_deck(deck, user_id, uow.library)
            return to_deck_output(deck)

    async def list_catalog(self, model: DeckCatalogInput) -> DeckCatalogOutput:
        async with self._uow_factory() as uow:
            decks, total = await uow.decks.list_catalog(model)
            return to_deck_catalog_output(decks, total)

    async def preview_by_share_code(self, share_code: str) -> DeckSharePreviewOutput:
        async with self._uow_factory() as uow:
            deck = await uow.decks.get_by_share_code(share_code)
            cards = await uow.cards.list_for_deck(deck.id)
            result = to_deck_share_preview_output(deck, cards)

            result.deck.cards_count = len(result.cards)
            return result

    async def update(
        self, user_id: int, deck_id: int, model: DeckUpdateInput
    ) -> DeckOutput:
        async with self._uow_factory() as uow:
            deck = await uow.decks.get_by_id(deck_id, for_update=True)
            require_author(deck, user_id)
            await uow.decks.update(deck, model)
            await uow.flush()
            result = to_deck_output(deck)
            await uow.commit()
            return result

    async def delete(self, user_id: int, deck_id: int) -> None:
        async with self._uow_factory() as uow:
            deck = await uow.decks.get_by_id(deck_id, for_update=True)
            require_author(deck, user_id)
            await uow.decks.delete(deck)
            await uow.commit()
