from typing import TYPE_CHECKING

from api.v1.flashcards.decks.contracts.mappers import to_deck_response
from api.v1.flashcards.library.contracts.responses import (
    LibraryListResponse,
    UserDeckResponse,
)
from application.flashcards.library.contracts.inputs import LibraryListInput

if TYPE_CHECKING:
    from api.v1.flashcards.library.contracts.requests import LibraryListRequest
    from application.flashcards.library.contracts.outputs import (
        LibraryListOutput,
        UserDeckOutput,
    )


def to_library_list_input(model: LibraryListRequest) -> LibraryListInput:
    return LibraryListInput.model_validate(
        {
            "search": model.search,
            "subject": model.subject.value if model.subject else None,
            "page": model.page,
            "limit": model.limit,
        }
    )


def to_library_list_response(model: LibraryListOutput) -> LibraryListResponse:
    return LibraryListResponse(
        items=[to_deck_response(deck) for deck in model.items],
        total=model.total,
    )


def to_user_deck_response(model: UserDeckOutput) -> UserDeckResponse:
    return UserDeckResponse(
        id=model.id,
        user_id=model.user_id,
        deck_id=model.deck_id,
        is_favorite=model.is_favorite,
        created_at=model.created_at,
    )
