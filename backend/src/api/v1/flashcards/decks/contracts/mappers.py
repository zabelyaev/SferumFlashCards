from typing import TYPE_CHECKING

from api.v1.flashcards.cards.contracts.mappers import to_card_response
from api.v1.flashcards.decks.contracts.responses import (
    DeckCatalogResponse,
    DeckResponse,
    DeckSharePreviewResponse,
)
from application.flashcards.decks.contracts.inputs import (
    DeckCatalogInput,
    DeckCreateInput,
    DeckUpdateInput,
)

if TYPE_CHECKING:
    from api.v1.flashcards.decks.contracts.requests import (
        DeckCatalogRequest,
        DeckCreateRequest,
        DeckUpdateRequest,
    )
    from application.flashcards.decks.contracts.outputs import (
        DeckCatalogOutput,
        DeckOutput,
        DeckSharePreviewOutput,
    )


def to_deck_input(model: DeckCreateRequest) -> DeckCreateInput:
    return DeckCreateInput.model_validate(
        {
            "title": model.title,
            "description": model.description,
            "subject": model.subject.value if model.subject is not None else None,
            "grade": model.grade,
            "exam_type": model.exam_type.value if model.exam_type else None,
            "cover_color": model.cover_color,
            "is_public": model.is_public,
        }
    )


def to_deck_update_input(model: DeckUpdateRequest) -> DeckUpdateInput:
    fields = (
        "title",
        "description",
        "subject",
        "grade",
        "exam_type",
        "cover_color",
        "is_public",
    )
    return DeckUpdateInput.model_validate(
        {
            field: getattr(model, field)
            for field in fields
            if field in model.model_fields_set
        }
    )


def to_deck_catalog_input(model: DeckCatalogRequest) -> DeckCatalogInput:
    return DeckCatalogInput.model_validate(
        {
            "search": model.search,
            "subject": model.subject.value if model.subject else None,
            "grade": model.grade,
            "exam_type": model.exam_type.value if model.exam_type else None,
            "page": model.page,
            "limit": model.limit,
        }
    )


def to_deck_response(model: DeckOutput) -> DeckResponse:
    return DeckResponse.model_validate(
        {
            "id": model.id,
            "author_id": model.author_id,
            "title": model.title,
            "description": model.description,
            "subject": model.subject.value if model.subject is not None else None,
            "grade": model.grade,
            "exam_type": model.exam_type.value if model.exam_type else None,
            "cover_color": model.cover_color,
            "is_public": model.is_public,
            "is_official": model.is_official,
            "share_code": model.share_code,
            "cards_count": model.cards_count,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
    )


def to_deck_catalog_response(model: DeckCatalogOutput) -> DeckCatalogResponse:
    return DeckCatalogResponse(
        items=[to_deck_response(deck) for deck in model.items],
        total=model.total,
    )


def to_deck_share_preview_response(
    model: DeckSharePreviewOutput,
) -> DeckSharePreviewResponse:
    return DeckSharePreviewResponse(
        deck=to_deck_response(model.deck),
        cards=[to_card_response(card) for card in model.cards],
    )
