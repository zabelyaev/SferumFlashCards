from pydantic import AwareDatetime

from api.types import BigIntId, NonNegativeInt32
from api.v1.flashcards.cards.contracts.responses import CardResponse
from api.v1.flashcards.decks.contracts.types import ExamType, Grade
from api.v1.flashcards.types import Subject
from common.schemas.base import BaseSchema


class DeckResponse(BaseSchema):
    id: BigIntId
    author_id: BigIntId | None
    title: str
    description: str | None
    subject: Subject | None
    grade: Grade | None
    exam_type: ExamType | None
    cover_color: str | None
    is_public: bool
    is_official: bool
    share_code: str
    cards_count: NonNegativeInt32
    created_at: AwareDatetime
    updated_at: AwareDatetime


class DeckCatalogResponse(BaseSchema):
    items: list[DeckResponse]
    total: int


class DeckSharePreviewResponse(BaseSchema):
    deck: DeckResponse
    cards: list[CardResponse]
