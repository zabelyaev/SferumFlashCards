from pydantic import AwareDatetime, HttpUrl

from api.types import BigIntId, NonNegativeInt32
from common.schemas.base import BaseSchema


class CardResponse(BaseSchema):
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


class CardListResponse(BaseSchema):
    items: list[CardResponse]
    total: int
