from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

type AppKey = Annotated[
    str, StringConstraints(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_-]+$")
]


class AuthConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_key: AppKey | None = Field(default=None, repr=False)

    @field_validator("app_key", mode="before")
    @classmethod
    def empty_key_is_unconfigured(cls, value: object) -> object:
        return None if value == "" else value
