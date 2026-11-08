from typing import Annotated

from pydantic import Field, StringConstraints, field_validator

from application.shared.contracts.types import BigIntId
from application.shared.enums import Subject
from common.schemas.base import BaseSchema
from common.schemas.patch import PatchSchema


class UserDeckCreateInput(BaseSchema):
    deck_id: BigIntId
    is_favorite: bool = False


class UserDeckUpdateInput(PatchSchema):
    is_favorite: bool | None = None


class LibraryListInput(BaseSchema):
    search: Annotated[str, StringConstraints(max_length=100)] | None = None
    subject: Subject | None = None
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
