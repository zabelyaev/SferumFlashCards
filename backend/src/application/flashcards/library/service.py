from __future__ import annotations

from typing import TYPE_CHECKING

from application.flashcards.library.contracts.mappers import (
    to_library_list_output,
    to_user_deck_output,
)
from application.flashcards.shared.policies import require_can_add_to_library

if TYPE_CHECKING:
    from application.flashcards.database.uow import FlashcardsUnitOfWorkFactory
    from application.flashcards.library.contracts.inputs import LibraryListInput
    from application.flashcards.library.contracts.outputs import (
        LibraryListOutput,
        UserDeckOutput,
    )


class LibraryService:
    def __init__(self, uow_factory: FlashcardsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def list_decks(
        self, user_id: int, model: LibraryListInput
    ) -> LibraryListOutput:
        async with self._uow_factory() as uow:
            decks, total = await uow.library.list_decks_for_user(user_id, model)
            return to_library_list_output(decks, total)

    async def add(self, user_id: int, deck_id: int) -> UserDeckOutput:
        async with self._uow_factory() as uow:
            deck = await uow.decks.get_by_id(deck_id, for_share=True)
            membership = None
            if deck.author_id != user_id and not deck.is_public:
                membership = await uow.library.find_membership(user_id, deck.id)
            require_can_add_to_library(deck, user_id, is_member=membership is not None)
            if membership is None:
                membership = await uow.library.ensure_membership(
                    user_id=user_id, deck_id=deck.id
                )
            await uow.flush()
            result = to_user_deck_output(membership)
            await uow.commit()
            return result

    async def add_by_share_code(self, user_id: int, share_code: str) -> UserDeckOutput:
        async with self._uow_factory() as uow:
            deck = await uow.decks.get_by_share_code(share_code, for_share=True)
            membership = await uow.library.ensure_membership(
                user_id=user_id, deck_id=deck.id
            )
            await uow.flush()
            result = to_user_deck_output(membership)
            await uow.commit()
            return result

    async def remove(self, user_id: int, deck_id: int) -> None:
        async with self._uow_factory() as uow:
            await uow.decks.get_by_id(deck_id, for_update=True)
            await uow.library.remove_membership(user_id=user_id, deck_id=deck_id)
            await uow.commit()
