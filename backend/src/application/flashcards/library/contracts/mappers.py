from typing import TYPE_CHECKING

from application.flashcards.decks.contracts.mappers import to_deck_output
from application.flashcards.library.contracts.outputs import (
    LibraryListOutput,
    UserDeckOutput,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.flashcards.decks.database.models import Deck
    from application.flashcards.library.database.models import UserDeck


def to_library_list_output(decks: Sequence[Deck], total: int) -> LibraryListOutput:
    return LibraryListOutput(
        items=[to_deck_output(deck) for deck in decks], total=total
    )


def to_user_deck_output(membership: UserDeck) -> UserDeckOutput:
    return UserDeckOutput(
        id=membership.id,
        user_id=membership.user_id,
        deck_id=membership.deck_id,
        is_favorite=membership.is_favorite,
        created_at=membership.created_at,
    )
