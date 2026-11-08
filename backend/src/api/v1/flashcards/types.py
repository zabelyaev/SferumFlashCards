from enum import StrEnum
from typing import Annotated

from pydantic import StringConstraints


class Subject(StrEnum):
    PHYSICS = "physics"
    ALGEBRA = "algebra"
    GEOMETRY = "geometry"
    CHEMISTRY = "chemistry"
    BIOLOGY = "biology"
    HISTORY = "history"
    RUSSIAN = "russian"
    INFORMATICS = "informatics"
    ENGLISH = "english"
    OTHER = "other"


type SearchText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=100, pattern=r"^[^\x00]*$")
]
type ShareCode = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{8}$")]
