from pydantic import AwareDatetime, HttpUrl

from application.shared.contracts.base import ReadSchema
from application.shared.contracts.types import (
    BigIntId,
    NonNegativeInt32,
    NonNegativeInt64,
)
from common.schemas.base import BaseSchema


class CardOutput(ReadSchema):
    id: BigIntId
    deck_id: BigIntId
    front: str
    back: str
    hint: str | None
    explanation: str | None
    image_url: HttpUrl | None
    order_index: NonNegativeInt32
    created_at: AwareDatetime
    updated_at: AwareDatetime


class CardListOutput(BaseSchema):
    items: list[CardOutput]
    total: NonNegativeInt64
