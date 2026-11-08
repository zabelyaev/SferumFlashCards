from pydantic import AwareDatetime

from api.types import BigIntId
from api.v1.flashcards.decks.contracts.responses import DeckResponse
from common.schemas.base import BaseSchema


class UserDeckResponse(BaseSchema):
    id: BigIntId
    user_id: BigIntId
    deck_id: BigIntId
    is_favorite: bool
    created_at: AwareDatetime


class LibraryListResponse(BaseSchema):
    items: list[DeckResponse]
    total: int
