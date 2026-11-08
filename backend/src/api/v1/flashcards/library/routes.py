from typing import Annotated

from fastapi import APIRouter, Query, status

from api.dependencies.auth import CurrentUserDep
from api.dependencies.services import LibraryServiceDep
from api.types import BigIntId
from api.v1.flashcards.library.contracts.mappers import (
    to_library_list_input,
    to_library_list_response,
    to_user_deck_response,
)
from api.v1.flashcards.library.contracts.requests import LibraryListRequest
from api.v1.flashcards.library.contracts.responses import (
    LibraryListResponse,
    UserDeckResponse,
)
from api.v1.flashcards.types import SearchText, ShareCode, Subject
from common.config import settings

router = APIRouter(
    prefix=f"{settings.api.v1.library}{settings.api.v1.decks}", tags=["Library"]
)


@router.get("")
async def list_library(
    user: CurrentUserDep,
    service: LibraryServiceDep,
    search: Annotated[SearchText | None, Query()] = None,
    subject: Subject | None = None,
    page: Annotated[int, Query(ge=1, le=2**31 - 1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> LibraryListResponse:
    model = to_library_list_input(
        LibraryListRequest(search=search, subject=subject, page=page, limit=limit)
    )
    return to_library_list_response(await service.list_decks(user.id, model))


@router.put(f"{settings.api.v1.share}/{{share_code}}")
async def add_shared_deck(
    share_code: ShareCode, user: CurrentUserDep, service: LibraryServiceDep
) -> UserDeckResponse:
    return to_user_deck_response(await service.add_by_share_code(user.id, share_code))


@router.put("/{deck_id}")
async def add_to_library(
    deck_id: BigIntId, user: CurrentUserDep, service: LibraryServiceDep
) -> UserDeckResponse:
    return to_user_deck_response(await service.add(user.id, deck_id))


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_library(
    deck_id: BigIntId, user: CurrentUserDep, service: LibraryServiceDep
) -> None:
    await service.remove(user.id, deck_id)
