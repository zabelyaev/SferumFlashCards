from typing import TYPE_CHECKING

from common.exceptions.forbidden import ForbiddenError

if TYPE_CHECKING:
    from application.flashcards.decks.database.models import Deck


def require_author(deck: Deck, actor_user_id: int) -> None:
    if deck.author_id != actor_user_id:
        raise ForbiddenError("Only the author may modify this deck.")


def can_read_deck(deck: Deck, actor_user_id: int, *, is_member: bool = False) -> bool:
    return deck.author_id == actor_user_id or deck.is_public or is_member


def require_can_add_to_library(
    deck: Deck, actor_user_id: int, *, is_member: bool = False
) -> None:
    if not can_read_deck(deck, actor_user_id, is_member=is_member):
        raise ForbiddenError("Deck is private.")
