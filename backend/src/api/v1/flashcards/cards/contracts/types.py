from typing import Annotated

from pydantic import AfterValidator, StringConstraints

from common.schemas.text import validate_postgres_text

type Content = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
    AfterValidator(validate_postgres_text),
]
