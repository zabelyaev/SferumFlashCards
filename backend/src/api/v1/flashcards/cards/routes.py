from typing import Annotated

from fastapi import APIRouter, Query, status

from api.dependencies.auth import CurrentUserDep
from api.dependencies.services import CardServiceDep
from api.types import BigIntId
from api.v1.flashcards.cards.contracts.mappers import (
    to_card_input,
    to_card_list_input,
    to_card_list_response,
    to_card_response,
    to_card_update_input,
)
from api.v1.flashcards.cards.contracts.requests import (
    CardCreateRequest,
    CardListRequest,
    CardUpdateRequest,
)
from api.v1.flashcards.cards.contracts.responses import CardListResponse, CardResponse
from common.config import settings

router = APIRouter(
    prefix=f"{settings.api.v1.decks}/{{deck_id}}{settings.api.v1.cards}", tags=["Cards"]
)


@router.get("")
async def list_cards(
    deck_id: BigIntId,
    user: CurrentUserDep,
    service: CardServiceDep,
    page: Annotated[int, Query(ge=1, le=2**31 - 1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CardListResponse:
    model = to_card_list_input(CardListRequest(page=page, limit=limit))
    return to_card_list_response(await service.list_for_deck(user.id, deck_id, model))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_card(
    deck_id: BigIntId,
    model: CardCreateRequest,
    user: CurrentUserDep,
    service: CardServiceDep,
) -> CardResponse:
    return to_card_response(
        await service.create(user.id, deck_id, to_card_input(model))
    )


@router.patch("/{card_id}")
async def update_card(
    deck_id: BigIntId,
    card_id: BigIntId,
    model: CardUpdateRequest,
    user: CurrentUserDep,
    service: CardServiceDep,
) -> CardResponse:
    return to_card_response(
        await service.update(user.id, deck_id, card_id, to_card_update_input(model))
    )


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    deck_id: BigIntId,
    card_id: BigIntId,
    user: CurrentUserDep,
    service: CardServiceDep,
) -> None:
    await service.delete(user.id, deck_id, card_id)
