from typing import TYPE_CHECKING

from pydantic import HttpUrl

from application.accounts.users.contracts.outputs import UserProfileOutput

if TYPE_CHECKING:
    from application.accounts.users.database.models import User


def to_user_profile_output(user: User) -> UserProfileOutput:
    return UserProfileOutput(
        id=user.id,
        vk_user_id=user.vk_user_id,
        first_name=user.first_name,
        last_name=user.last_name,
        avatar_url=HttpUrl(user.avatar_url) if user.avatar_url is not None else None,
        role=user.role,
        is_active=user.is_active,
        timezone=user.timezone,
        streak_days=user.streak_days,
        max_streak_days=user.max_streak_days,
        last_streak_date=user.last_streak_date,
        daily_total_cards_limit=user.daily_total_cards_limit,
        daily_new_cards_limit=user.daily_new_cards_limit,
        settings=user.settings,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
