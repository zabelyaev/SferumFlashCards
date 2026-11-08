from typing import TYPE_CHECKING

from application.flashcards.cards.contracts.mappers import to_card_output
from application.flashcards.decks.contracts.outputs import (
    DeckCatalogOutput,
    DeckOutput,
    DeckSharePreviewOutput,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.flashcards.cards.database.models import Card
    from application.flashcards.decks.database.models import Deck


def to_deck_output(deck: Deck) -> DeckOutput:
    return DeckOutput(
        id=deck.id,
        author_id=deck.author_id,
        title=deck.title,
        description=deck.description,
        subject=deck.subject,
        grade=deck.grade,
        exam_type=deck.exam_type,
        cover_color=deck.cover_color,
        is_public=deck.is_public,
        is_official=deck.is_official,
        share_code=deck.share_code,
        cards_count=deck.cards_count,
        created_at=deck.created_at,
        updated_at=deck.updated_at,
    )


def to_deck_catalog_output(decks: Sequence[Deck], total: int) -> DeckCatalogOutput:
    return DeckCatalogOutput(
        items=[to_deck_output(deck) for deck in decks], total=total
    )


def to_deck_share_preview_output(
    deck: Deck, cards: Sequence[Card]
) -> DeckSharePreviewOutput:
    return DeckSharePreviewOutput(
        deck=to_deck_output(deck),
        cards=[to_card_output(card) for card in cards],
    )
