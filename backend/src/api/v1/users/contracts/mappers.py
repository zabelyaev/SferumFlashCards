from typing import TYPE_CHECKING

from api.types import UserRole
from api.v1.users.contracts.responses import UserProfileResponse
from application.accounts.users.contracts.inputs import (
    UserProfileUpdateInput,
    UserSettingsReplaceInput,
    UserSyncInput,
)
from application.shared.enums import UserRole as ApplicationUserRole

if TYPE_CHECKING:
    from api.v1.users.contracts.requests import (
        UserProfileUpdateRequest,
        UserSettingsReplaceRequest,
        UserSyncRequest,
    )
    from application.accounts.users.contracts.outputs import UserProfileOutput

ROLE_TO_RESPONSE: dict[ApplicationUserRole, UserRole] = {
    ApplicationUserRole.STUDENT: UserRole.STUDENT,
    ApplicationUserRole.TEACHER: UserRole.TEACHER,
    ApplicationUserRole.ADMIN: UserRole.ADMIN,
}


def to_user_sync_input(model: UserSyncRequest) -> UserSyncInput:
    data: dict[str, object] = {"vk_user_id": model.vk_user_id}
    for field in ("first_name", "last_name", "avatar_url", "timezone"):
        if field in model.model_fields_set:
            data[field] = getattr(model, field)
    return UserSyncInput.model_validate(data)


def to_user_profile_update_input(
    model: UserProfileUpdateRequest,
) -> UserProfileUpdateInput:
    data = {
        field: getattr(model, field)
        for field in (
            "first_name",
            "last_name",
            "avatar_url",
            "timezone",
            "daily_total_cards_limit",
            "daily_new_cards_limit",
        )
        if field in model.model_fields_set
    }
    return UserProfileUpdateInput.model_validate(data)


def to_user_settings_replace_input(
    model: UserSettingsReplaceRequest,
) -> UserSettingsReplaceInput:
    return UserSettingsReplaceInput.model_validate({"settings": model.root})


def to_user_profile_response(model: UserProfileOutput) -> UserProfileResponse:
    return UserProfileResponse(
        id=model.id,
        vk_user_id=model.vk_user_id,
        first_name=model.first_name,
        last_name=model.last_name,
        avatar_url=model.avatar_url,
        role=ROLE_TO_RESPONSE[model.role],
        is_active=model.is_active,
        timezone=model.timezone,
        streak_days=model.streak_days,
        max_streak_days=model.max_streak_days,
        last_streak_date=model.last_streak_date,
        daily_total_cards_limit=model.daily_total_cards_limit,
        daily_new_cards_limit=model.daily_new_cards_limit,
        settings=model.settings,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
