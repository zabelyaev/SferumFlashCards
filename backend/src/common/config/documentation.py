import re
from typing import TYPE_CHECKING

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

if TYPE_CHECKING:
    from typing import Self


class DocumentationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    prefix: str = "/internal"
    password: SecretStr = Field(default_factory=lambda: SecretStr(""))
    login: str = ""
    enabled: bool = False

    @field_validator("prefix")
    @classmethod
    def normalize_prefix(cls, value: str) -> str:
        prefix = "/" + value.strip().strip("/")
        if re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+", prefix) is None:
            raise ValueError(
                "Documentation prefix must contain non-empty URL path segments "
                "using letters, digits, hyphens or underscores."
            )
        return prefix

    @model_validator(mode="after")
    def validate_credentials(self) -> Self:
        if self.enabled:
            password = self.password.get_secret_value()
            if not self.login.strip() or not password.strip():
                raise ValueError("Enabled documentation requires a login and password.")
            if ":" in self.login or any(
                not value.isascii() or not value.isprintable()
                for value in (self.login, password)
            ):
                raise ValueError(
                    "Documentation credentials must be printable ASCII; "
                    "the login cannot contain a colon."
                )
        return self
