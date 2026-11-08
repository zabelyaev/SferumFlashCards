from typing import TYPE_CHECKING

from application.flashcards.shared.policies import can_read_deck
from common.exceptions.forbidden import ForbiddenError

if TYPE_CHECKING:
    from application.flashcards.database.uow import LibraryRepository
    from application.flashcards.decks.database.models import Deck


async def require_readable_deck(
    deck: Deck, actor_user_id: int, library: LibraryRepository
) -> None:
    if can_read_deck(deck, actor_user_id):
        return
    membership = await library.find_membership(actor_user_id, deck.id)
    if not can_read_deck(deck, actor_user_id, is_member=membership is not None):
        raise ForbiddenError("Deck is private.")
