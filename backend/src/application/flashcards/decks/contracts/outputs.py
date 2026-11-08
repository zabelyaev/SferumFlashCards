from pydantic import AwareDatetime

from application.flashcards.cards.contracts.outputs import CardOutput
from application.flashcards.decks.contracts.types import (
    CoverColor,
    Description,
    ShareCode,
)
from application.shared.contracts.base import ReadSchema
from application.shared.contracts.types import (
    BigIntId,
    Grade,
    NonNegativeInt32,
    NonNegativeInt64,
    ShortName,
)
from application.shared.enums import ExamType, Subject
from common.schemas.base import BaseSchema


class DeckOutput(ReadSchema):
    id: BigIntId
    author_id: BigIntId | None
    title: ShortName
    description: Description | None
    subject: Subject | None
    grade: Grade | None
    exam_type: ExamType | None
    cover_color: CoverColor | None
    is_public: bool
    is_official: bool
    share_code: ShareCode
    cards_count: NonNegativeInt32
    created_at: AwareDatetime
    updated_at: AwareDatetime


class DeckCatalogOutput(BaseSchema):
    items: list[DeckOutput]
    total: NonNegativeInt64


class DeckSharePreviewOutput(BaseSchema):
    deck: DeckOutput
    cards: list[CardOutput]
