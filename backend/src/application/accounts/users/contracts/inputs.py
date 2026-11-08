from typing import ClassVar

from pydantic import ConfigDict, Field, HttpUrl, JsonValue, model_validator

from application.shared.contracts.types import (
    BigIntId,
    DailyNewCardsLimit,
    DailyTotalCardsLimit,
    ProfileName,
    TimezoneName,
)
from common.schemas.base import BaseSchema
from common.schemas.json_values import validate_postgres_json
from common.schemas.patch import PatchSchema


class UserSyncInput(BaseSchema):
    vk_user_id: BigIntId
    first_name: ProfileName = ""
    last_name: ProfileName = ""
    avatar_url: HttpUrl | None = None
    timezone: TimezoneName = "UTC"


class UserProfileUpdateInput(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"avatar_url"})

    first_name: ProfileName | None = None
    last_name: ProfileName | None = None
    avatar_url: HttpUrl | None = None
    timezone: TimezoneName | None = None
    daily_total_cards_limit: DailyTotalCardsLimit | None = None
    daily_new_cards_limit: DailyNewCardsLimit | None = None


class UserSettingsReplaceInput(BaseSchema):
    model_config = ConfigDict(allow_inf_nan=False)

    settings: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_settings(self) -> UserSettingsReplaceInput:
        validate_postgres_json(self.settings)
        return self
