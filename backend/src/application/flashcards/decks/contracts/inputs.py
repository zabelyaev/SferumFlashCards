from typing import Annotated, ClassVar

from pydantic import Field, StringConstraints, field_validator

from application.flashcards.decks.contracts.types import CoverColor, Description
from application.shared.contracts.types import Grade, ShortName
from application.shared.enums import ExamType, Subject
from common.schemas.base import BaseSchema
from common.schemas.patch import PatchSchema


class DeckCreateInput(BaseSchema):
    title: ShortName
    description: Description | None = None
    subject: Subject | None = None
    grade: Grade | None = None
    exam_type: ExamType | None = None
    cover_color: CoverColor | None = None
    is_public: bool = False


class DeckUpdateInput(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset(
        {"description", "subject", "grade", "exam_type", "cover_color"}
    )

    title: ShortName | None = None
    description: Description | None = None
    subject: Subject | None = None
    grade: Grade | None = None
    exam_type: ExamType | None = None
    cover_color: CoverColor | None = None
    is_public: bool | None = None


class DeckCatalogInput(BaseSchema):
    search: Annotated[str, StringConstraints(max_length=100)] | None = None
    subject: Subject | None = None
    grade: Grade | None = None
    exam_type: ExamType | None = None
    page: Annotated[int, Field(strict=True, ge=1, le=2**31 - 1)] = 1
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 20

    @field_validator("search", mode="before")
    @classmethod
    def normalize_search(cls, value: object) -> object:
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("Search must not contain NUL characters.")
            return value.strip() or None
        return value
