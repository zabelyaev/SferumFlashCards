from typing import Annotated

from pydantic import StringConstraints

from application.shared.contracts.types import BigIntId, Rating
from common.schemas.base import BaseSchema


class StudySessionCreateInput(BaseSchema):
    deck_id: BigIntId


class ReviewCreateInput(BaseSchema):
    card_id: BigIntId
    rating: Rating
    answer_token: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    ]
