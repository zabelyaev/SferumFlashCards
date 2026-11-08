from typing import Annotated, ClassVar

from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema

from api.v1.flashcards.decks.contracts.types import (
    CoverColor,
    Description,
    ExamType,
    Grade,
    Title,
)
from api.v1.flashcards.types import SearchText, Subject
from common.schemas.base import BaseSchema
from common.schemas.patch import PatchSchema


class DeckCreateRequest(BaseSchema):
    title: Title
    description: Description | None = None
    subject: Subject | None = None
    grade: Grade | None = None
    exam_type: ExamType | None = None
    cover_color: CoverColor | None = None
    is_public: bool = False


class DeckUpdateRequest(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset(
        {"description", "subject", "grade", "exam_type", "cover_color"}
    )

    title: Title | SkipJsonSchema[None] = None
    description: Description | None = None
    subject: Subject | None = None
    grade: Grade | None = None
    exam_type: ExamType | None = None
    cover_color: CoverColor | None = None
    is_public: bool | SkipJsonSchema[None] = None


class DeckCatalogRequest(BaseSchema):
    search: SearchText | None = None
    subject: Subject | None = None
    grade: Annotated[int, Field(ge=7, le=11)] | None = None
    exam_type: ExamType | None = None
    page: Annotated[int, Field(ge=1, le=2**31 - 1)] = 1
    limit: Annotated[int, Field(ge=1, le=100)] = 20

    @field_validator("search")
    @classmethod
    def empty_search_is_absent(cls, value: str | None) -> str | None:
        return value or None
