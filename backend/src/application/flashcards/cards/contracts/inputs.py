from typing import Annotated, ClassVar

from pydantic import Field, HttpUrl

from application.flashcards.cards.contracts.types import CardContent
from common.schemas.base import BaseSchema
from common.schemas.patch import PatchSchema
from common.schemas.text import PostgresText


class CardCreateInput(BaseSchema):
    front: CardContent
    back: CardContent
    hint: PostgresText | None = None
    explanation: PostgresText | None = None
    image_url: HttpUrl | None = None


class CardUpdateInput(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset(
        {"hint", "explanation", "image_url"}
    )

    front: CardContent | None = None
    back: CardContent | None = None
    hint: PostgresText | None = None
    explanation: PostgresText | None = None
    image_url: HttpUrl | None = None


class CardListInput(BaseSchema):
    page: Annotated[int, Field(strict=True, ge=1, le=2**31 - 1)] = 1
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 20
