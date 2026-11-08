from pydantic import AwareDatetime

from application.flashcards.decks.contracts.outputs import DeckOutput
from application.shared.contracts.base import ReadSchema
from application.shared.contracts.types import (
    BigIntId,
    NonNegativeInt32,
    NonNegativeInt64,
)
from common.schemas.base import BaseSchema


class UserDeckOutput(ReadSchema):
    id: BigIntId
    user_id: BigIntId
    deck_id: BigIntId
    is_favorite: bool
    created_at: AwareDatetime


class LibraryListOutput(BaseSchema):
    items: list[DeckOutput]
    total: NonNegativeInt64


class UserDeckProgressOutput(BaseSchema):
    deck_id: BigIntId
    cards_count: NonNegativeInt32
    due_count: NonNegativeInt32
    new_count: NonNegativeInt32
    mastered_count: NonNegativeInt32
