from typing import TYPE_CHECKING, ClassVar

from pydantic import (
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
    RootModel,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema

from api.types import (
    BigIntId,
    DailyNewCardsLimit,
    DailyTotalCardsLimit,
    ProfileName,
    TimezoneName,
)
from common.schemas.base import BaseSchema
from common.schemas.json_values import (
    MAX_JSON_NESTING_DEPTH,
    validate_postgres_json,
)
from common.schemas.patch import PatchSchema

if TYPE_CHECKING:
    from typing import Self


class UserSyncRequest(BaseSchema):
    vk_user_id: BigIntId
    first_name: ProfileName = ""
    last_name: ProfileName = ""
    avatar_url: HttpUrl | None = None
    timezone: TimezoneName = "UTC"


class UserSettingsReplaceRequest(RootModel[dict[str, JsonValue]]):
    model_config = ConfigDict(allow_inf_nan=False)

    root: dict[str, JsonValue] = Field(
        default_factory=dict,
        description=(
            "Settings object. Values may contain at most "
            f"{MAX_JSON_NESTING_DEPTH} nested arrays or objects below this root."
        ),
    )

    @model_validator(mode="after")
    def validate_settings(self) -> Self:
        validate_postgres_json(self.root)
        return self


class UserProfileUpdateRequest(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"avatar_url"})

    first_name: ProfileName | SkipJsonSchema[None] = None
    last_name: ProfileName | SkipJsonSchema[None] = None
    avatar_url: HttpUrl | None = None
    timezone: TimezoneName | SkipJsonSchema[None] = None
    daily_total_cards_limit: DailyTotalCardsLimit | SkipJsonSchema[None] = None
    daily_new_cards_limit: DailyNewCardsLimit | SkipJsonSchema[None] = None
