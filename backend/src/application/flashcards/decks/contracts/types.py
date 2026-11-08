from typing import Annotated

from pydantic import AfterValidator, StringConstraints

from common.schemas.text import validate_postgres_text

type Description = Annotated[
    str, StringConstraints(max_length=300), AfterValidator(validate_postgres_text)
]
type CoverColor = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=32),
    AfterValidator(validate_postgres_text),
]
type ShareCode = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{8}$")]
