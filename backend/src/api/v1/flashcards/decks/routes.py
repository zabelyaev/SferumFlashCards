from typing import Annotated

from fastapi import APIRouter, Query, status

from api.dependencies.auth import CurrentUserDep
from api.dependencies.services import DeckServiceDep
from api.types import BigIntId
from api.v1.flashcards.decks.contracts.mappers import (
    to_deck_catalog_input,
    to_deck_catalog_response,
    to_deck_input,
    to_deck_response,
    to_deck_share_preview_response,
    to_deck_update_input,
)
from api.v1.flashcards.decks.contracts.requests import (
    DeckCatalogRequest,
    DeckCreateRequest,
    DeckUpdateRequest,
)
from api.v1.flashcards.decks.contracts.responses import (
    DeckCatalogResponse,
    DeckResponse,
    DeckSharePreviewResponse,
)
from api.v1.flashcards.decks.contracts.types import ExamType
from api.v1.flashcards.types import SearchText, ShareCode, Subject
from common.config import settings

router = APIRouter(prefix=settings.api.v1.decks, tags=["Decks"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_deck(
    model: DeckCreateRequest, user: CurrentUserDep, service: DeckServiceDep
) -> DeckResponse:
    return to_deck_response(await service.create(user.id, to_deck_input(model)))


@router.get("")
async def list_catalog(
    service: DeckServiceDep,
    search: Annotated[SearchText | None, Query()] = None,
    subject: Subject | None = None,
    grade: Annotated[int | None, Query(ge=7, le=11)] = None,
    exam_type: ExamType | None = None,
    page: Annotated[int, Query(ge=1, le=2**31 - 1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DeckCatalogResponse:
    model = DeckCatalogRequest(
        search=search,
        subject=subject,
        grade=grade,
        exam_type=exam_type,
        page=page,
        limit=limit,
    )
    return to_deck_catalog_response(
        await service.list_catalog(to_deck_catalog_input(model))
    )


@router.get(f"{settings.api.v1.share}/{{share_code}}")
async def preview_shared_deck(
    share_code: ShareCode, service: DeckServiceDep
) -> DeckSharePreviewResponse:
    return to_deck_share_preview_response(
        await service.preview_by_share_code(share_code)
    )


@router.get("/{deck_id}")
async def get_deck(
    deck_id: BigIntId, user: CurrentUserDep, service: DeckServiceDep
) -> DeckResponse:
    return to_deck_response(await service.get(user.id, deck_id))


@router.patch("/{deck_id}")
async def update_deck(
    deck_id: BigIntId,
    model: DeckUpdateRequest,
    user: CurrentUserDep,
    service: DeckServiceDep,
) -> DeckResponse:
    return to_deck_response(
        await service.update(user.id, deck_id, to_deck_update_input(model))
    )


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deck(
    deck_id: BigIntId, user: CurrentUserDep, service: DeckServiceDep
) -> None:
    await service.delete(user.id, deck_id)
