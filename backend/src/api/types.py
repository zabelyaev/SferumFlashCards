from enum import StrEnum
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, Field, StringConstraints

from common.schemas.text import validate_postgres_text

BIGINT_MAX = 2**63 - 1


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError("Unknown IANA timezone.") from error
    return value


type BigIntId = Annotated[int, Field(gt=0, le=BIGINT_MAX)]
type ProfileName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=100),
    AfterValidator(validate_postgres_text),
]
type NonNegativeInt32 = Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)]
type DailyTotalCardsLimit = Annotated[int, Field(strict=True, ge=20, le=1000)]
type DailyNewCardsLimit = Annotated[int, Field(strict=True, ge=1, le=250)]

type TimezoneName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64),
    AfterValidator(validate_timezone),
]


class UserRole(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
