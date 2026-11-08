from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from common.schemas.text import validate_postgres_text


class ExamType(StrEnum):
    OGE = "oge"
    EGE = "ege"


type Title = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(validate_postgres_text),
]
type Description = Annotated[
    str, StringConstraints(max_length=300), AfterValidator(validate_postgres_text)
]
type Grade = Annotated[int, Field(strict=True, ge=7, le=11)]
type CoverColor = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=32),
    AfterValidator(validate_postgres_text),
]
