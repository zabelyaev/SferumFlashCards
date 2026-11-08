from typing import Annotated, ClassVar

from pydantic import Field, HttpUrl
from pydantic.json_schema import SkipJsonSchema

from api.v1.flashcards.cards.contracts.types import Content
from common.schemas.base import BaseSchema
from common.schemas.patch import PatchSchema
from common.schemas.text import PostgresText


class CardCreateRequest(BaseSchema):
    front: Content
    back: Content
    hint: PostgresText | None = None
    explanation: PostgresText | None = None
    image_url: HttpUrl | None = None


class CardUpdateRequest(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset(
        {"hint", "explanation", "image_url"}
    )

    front: Content | SkipJsonSchema[None] = None
    back: Content | SkipJsonSchema[None] = None
    hint: PostgresText | None = None
    explanation: PostgresText | None = None
    image_url: HttpUrl | None = None


class CardListRequest(BaseSchema):
    page: Annotated[int, Field(ge=1, le=2**31 - 1)] = 1
    limit: Annotated[int, Field(ge=1, le=100)] = 20
