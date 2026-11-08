from typing import Annotated

from pydantic import AfterValidator


def validate_postgres_text(value: str) -> str:
    if "\x00" in value:
        raise ValueError("Text cannot contain NUL characters.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("Text must contain valid Unicode.") from error
    return value


type PostgresText = Annotated[str, AfterValidator(validate_postgres_text)]
