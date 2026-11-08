from typing import Annotated

from pydantic import Field, field_validator

from api.v1.flashcards.types import SearchText, Subject
from common.schemas.base import BaseSchema


class LibraryListRequest(BaseSchema):
    search: SearchText | None = None
    subject: Subject | None = None
    page: Annotated[int, Field(ge=1, le=2**31 - 1)] = 1
    limit: Annotated[int, Field(ge=1, le=100)] = 20

    @field_validator("search")
    @classmethod
    def empty_search_is_absent(cls, value: str | None) -> str | None:
        return value or None
