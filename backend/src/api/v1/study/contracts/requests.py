from typing import Annotated

from pydantic import Field, StringConstraints

from api.types import (
    BigIntId,
)
from common.schemas.base import BaseSchema


class OpenSessionRequest(BaseSchema):
    deck_id: BigIntId


class ReviewRequest(BaseSchema):
    card_id: BigIntId
    rating: Annotated[int, Field(strict=True, ge=1, le=4)]
    answer_token: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    ]
