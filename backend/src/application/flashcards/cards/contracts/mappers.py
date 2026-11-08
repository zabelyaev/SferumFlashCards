from typing import TYPE_CHECKING

from pydantic import HttpUrl

from application.flashcards.cards.contracts.outputs import CardListOutput, CardOutput

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.flashcards.cards.database.models import Card


def to_card_output(card: Card) -> CardOutput:
    return CardOutput(
        id=card.id,
        deck_id=card.deck_id,
        front=card.front,
        back=card.back,
        hint=card.hint,
        explanation=card.explanation,
        image_url=HttpUrl(card.image_url) if card.image_url is not None else None,
        order_index=card.order_index,
        created_at=card.created_at,
        updated_at=card.updated_at,
    )


def to_card_list_output(cards: Sequence[Card], total: int) -> CardListOutput:
    return CardListOutput(items=[to_card_output(card) for card in cards], total=total)
