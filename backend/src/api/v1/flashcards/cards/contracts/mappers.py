from typing import TYPE_CHECKING

from api.v1.flashcards.cards.contracts.responses import CardListResponse, CardResponse
from application.flashcards.cards.contracts.inputs import (
    CardCreateInput,
    CardListInput,
    CardUpdateInput,
)

if TYPE_CHECKING:
    from api.v1.flashcards.cards.contracts.requests import (
        CardCreateRequest,
        CardListRequest,
        CardUpdateRequest,
    )
    from application.flashcards.cards.contracts.outputs import (
        CardListOutput,
        CardOutput,
    )


def to_card_input(model: CardCreateRequest) -> CardCreateInput:
    return CardCreateInput(
        front=model.front,
        back=model.back,
        hint=model.hint,
        explanation=model.explanation,
        image_url=model.image_url,
    )


def to_card_list_input(model: CardListRequest) -> CardListInput:
    return CardListInput(page=model.page, limit=model.limit)


def to_card_update_input(model: CardUpdateRequest) -> CardUpdateInput:
    fields = ("front", "back", "hint", "explanation", "image_url")
    return CardUpdateInput.model_validate(
        {
            field: getattr(model, field)
            for field in fields
            if field in model.model_fields_set
        }
    )


def to_card_response(model: CardOutput) -> CardResponse:
    return CardResponse(
        id=model.id,
        deck_id=model.deck_id,
        front=model.front,
        back=model.back,
        hint=model.hint,
        explanation=model.explanation,
        image_url=model.image_url,
        order_index=model.order_index,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def to_card_list_response(model: CardListOutput) -> CardListResponse:
    return CardListResponse(
        items=[to_card_response(card) for card in model.items],
        total=model.total,
    )
