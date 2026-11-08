from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from application.accounts.users.contracts.inputs import (
    UserProfileUpdateInput,
    UserSettingsReplaceInput,
    UserSyncInput,
)
from application.accounts.users.contracts.outputs import CurrentUserOutput
from application.accounts.users.database.models import User
from application.accounts.users.service import UserService
from application.activity.service import StreakService
from common.exceptions.forbidden import ForbiddenError
from common.exceptions.unauthorized import UnauthorizedError


def make_uow():
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.activity.completed_days.return_value = set()
    uow.activity.pending_days.return_value = set()

    async def update(user, *, profile):
        for field, value in profile.items():
            setattr(user, field, value)

    async def replace_settings(user, *, data):
        user.settings = dict(data.settings)

    uow.users.update.side_effect = update
    uow.users.replace_settings.side_effect = replace_settings
    return uow


async def test_sync_does_not_reset_omitted_profile_fields(profile) -> None:
    uow = make_uow()
    uow.users.upsert_by_vk_id.return_value = User(**profile.model_dump())
    service = UserService(lambda: uow, streak_factory=StreakService)
    result = await service.sync(UserSyncInput(vk_user_id=12345678))
    assert result.first_name == "Иван"
    uow.users.upsert_by_vk_id.assert_awaited_once_with(12345678, profile={})
    uow.commit.assert_awaited_once()


async def test_sync_passes_only_explicit_fields_including_null(profile) -> None:
    uow = make_uow()
    uow.users.upsert_by_vk_id.return_value = User(**profile.model_dump())
    await UserService(lambda: uow, streak_factory=StreakService).sync(
        UserSyncInput(vk_user_id=12345678, first_name="  Анна  ", avatar_url=None)
    )
    uow.users.upsert_by_vk_id.assert_awaited_once_with(
        12345678, profile={"first_name": "Анна", "avatar_url": None}
    )
    uow.commit.assert_awaited_once()


async def test_unknown_user_is_not_created_by_profile_lookup() -> None:
    uow = make_uow()
    uow.users.find_current_by_vk_id.return_value = None
    with pytest.raises(UnauthorizedError):
        await UserService(lambda: uow, streak_factory=StreakService).get_current(
            12345678
        )
    uow.users.upsert_by_vk_id.assert_not_awaited()
    uow.commit.assert_not_awaited()
    uow.activity.completed_days.assert_not_awaited()
    uow.flush.assert_not_awaited()
    uow.users.find_by_vk_id.assert_not_awaited()


async def test_disabled_user_is_rejected(profile) -> None:
    uow = make_uow()
    uow.users.find_current_by_vk_id.return_value = CurrentUserOutput(
        id=profile.id, is_active=False
    )
    with pytest.raises(ForbiddenError):
        await UserService(lambda: uow, streak_factory=StreakService).get_current(
            12345678
        )
    uow.flush.assert_not_awaited()
    uow.commit.assert_not_awaited()


async def test_auth_returns_only_current_user_projection() -> None:
    uow = make_uow()
    current = CurrentUserOutput(id=7, is_active=True)
    uow.users.find_current_by_vk_id.return_value = current
    result = await UserService(lambda: uow, streak_factory=StreakService).get_current(
        12345678
    )
    assert result is current
    assert result.model_dump() == {"id": 7, "is_active": True}
    uow.users.find_current_by_vk_id.assert_awaited_once_with(12345678)
    uow.users.find_by_vk_id.assert_not_awaited()
    uow.activity.completed_days.assert_not_awaited()
    uow.activity.pending_days.assert_not_awaited()
    uow.flush.assert_not_awaited()
    uow.commit.assert_not_awaited()


async def test_profile_update_clears_avatar_and_commits(profile) -> None:
    uow = make_uow()
    user = User(**profile.model_dump())
    uow.users.get_by_id.return_value = user
    await UserService(lambda: uow, streak_factory=StreakService).update(
        7, UserProfileUpdateInput(avatar_url=None)
    )
    uow.users.get_by_id.assert_awaited_once_with(7, no_key_update=True)
    uow.users.update.assert_awaited_once_with(user, profile={"avatar_url": None})
    uow.flush.assert_awaited_once()
    uow.commit.assert_awaited_once()


async def test_profile_update_passes_timezone_and_daily_limit(profile) -> None:
    uow = make_uow()
    user = User(**profile.model_dump())
    uow.users.get_by_id.return_value = user
    await UserService(lambda: uow, streak_factory=StreakService).update(
        7, UserProfileUpdateInput(timezone="Europe/Moscow", daily_new_cards_limit=30)
    )
    uow.users.update.assert_awaited_once_with(
        user, profile={"timezone": "Europe/Moscow", "daily_new_cards_limit": 30}
    )
    uow.activity.completed_days.assert_awaited_once_with(7)
    uow.commit.assert_awaited_once()


@pytest.mark.parametrize("stale", [False, True])
async def test_unchanged_timezone_update_uses_current_streak_path(
    profile, stale: bool
) -> None:
    uow = make_uow()
    user = User(**profile.model_dump())
    user.streak_days = user.max_streak_days = 1
    user.last_streak_date = datetime.now(UTC).date() - timedelta(days=2 if stale else 0)
    uow.users.get_by_id.return_value = user
    result = await UserService(lambda: uow, streak_factory=StreakService).update(
        user.id, UserProfileUpdateInput(timezone=user.timezone)
    )
    uow.users.get_by_id.assert_awaited_once_with(user.id, no_key_update=True)
    uow.activity.completed_days.assert_not_awaited()
    assert uow.activity.pending_days.await_count == int(stale)
    assert result.streak_days == (0 if stale else 1)
    assert result.last_streak_date == user.last_streak_date
    uow.flush.assert_awaited_once()


async def test_timezone_change_still_rebuilds_zero_streak_from_history(profile) -> None:
    uow = make_uow()
    user = User(**profile.model_dump())
    user.max_streak_days = 5
    timezone = "Pacific/Kiritimati"
    yesterday = datetime.now(ZoneInfo(timezone)).date() - timedelta(days=1)
    uow.users.get_by_id.return_value = user
    uow.activity.completed_days.return_value = {yesterday}
    result = await UserService(lambda: uow, streak_factory=StreakService).update(
        user.id, UserProfileUpdateInput(timezone=timezone)
    )
    uow.activity.completed_days.assert_awaited_once_with(user.id)
    uow.activity.pending_days.assert_awaited_once_with(user.id, ANY)
    assert (result.streak_days, result.max_streak_days, result.last_streak_date) == (
        1,
        5,
        yesterday,
    )


async def test_get_profile_locks_user_before_refresh(profile) -> None:
    uow = make_uow()
    uow.users.get_by_id.return_value = User(**profile.model_dump())
    result = await UserService(lambda: uow, streak_factory=StreakService).get_profile(7)
    uow.users.get_by_id.assert_awaited_once_with(7, no_key_update=True)
    uow.activity.completed_days.assert_not_awaited()
    uow.activity.pending_days.assert_not_awaited()
    uow.commit.assert_awaited_once()
    assert result.id == 7


async def test_replace_settings_does_not_read_activity_for_current_streak(
    profile,
) -> None:
    uow = make_uow()
    user = User(**profile.model_dump())
    uow.users.get_by_id.return_value = user
    model = UserSettingsReplaceInput(settings={"timezone": "client-only"})
    await UserService(lambda: uow, streak_factory=StreakService).replace_settings(
        7, model
    )
    uow.users.get_by_id.assert_awaited_once_with(7, no_key_update=True)
    uow.users.replace_settings.assert_awaited_once_with(user, data=model)
    uow.activity.completed_days.assert_not_awaited()
    uow.activity.pending_days.assert_not_awaited()
    uow.commit.assert_awaited_once()
    uow.flush.assert_awaited_once()


async def test_sync_recalculates_only_when_timezone_explicit(profile) -> None:
    uow = make_uow()
    uow.users.upsert_by_vk_id.return_value = User(**profile.model_dump())
    await UserService(lambda: uow, streak_factory=StreakService).sync(
        UserSyncInput(vk_user_id=12345678)
    )
    uow.activity.completed_days.assert_not_awaited()
    await UserService(lambda: uow, streak_factory=StreakService).sync(
        UserSyncInput(vk_user_id=12345678, timezone="UTC")
    )
    uow.activity.completed_days.assert_awaited_once_with(7)


async def test_injected_streak_factory_receives_active_uow_repository(profile) -> None:
    uow = make_uow()
    user = User(**profile.model_dump())
    uow.users.get_by_id.return_value = user
    streaks = AsyncMock(spec=StreakService)

    def bind(repo):
        uow.__aenter__.assert_awaited_once()
        uow.commit.assert_not_awaited()
        assert repo is uow.activity
        return streaks

    factory = MagicMock(side_effect=bind)
    await UserService(lambda: uow, streak_factory=factory).replace_settings(
        7, UserSettingsReplaceInput(settings={"theme": "dark"})
    )
    factory.assert_called_once_with(uow.activity)
    streaks.ensure_current.assert_awaited_once_with(user, ANY)
    streaks.recalculate.assert_not_awaited()
    uow.commit.assert_awaited_once()


@pytest.mark.parametrize("operation", ["profile", "sync", "update", "settings"])
async def test_user_mapping_follows_streak_refresh_and_single_flush(
    profile, operation: str
) -> None:
    uow = make_uow()
    user = User(**profile.model_dump())
    user.streak_days = user.max_streak_days = 1
    user.last_streak_date = datetime.now(UTC).date() - timedelta(days=2)
    uow.users.get_by_id.return_value = user
    uow.users.upsert_by_vk_id.return_value = user
    updated_at = datetime.now(UTC)

    async def flush():
        uow.activity.pending_days.assert_awaited_once_with(user.id, ANY)
        uow.commit.assert_not_awaited()
        assert user.streak_days == 0
        user.updated_at = updated_at

    uow.flush.side_effect = flush
    service = UserService(lambda: uow, streak_factory=StreakService)
    if operation == "profile":
        result = await service.get_profile(user.id)
    elif operation == "sync":
        result = await service.sync(UserSyncInput(vk_user_id=user.vk_user_id))
    elif operation == "update":
        result = await service.update(
            user.id, UserProfileUpdateInput(first_name="Анна")
        )
    else:
        result = await service.replace_settings(
            user.id, UserSettingsReplaceInput(settings={"theme": "dark"})
        )
    assert result.streak_days == 0
    assert result.updated_at == updated_at
    uow.flush.assert_awaited_once()
    uow.commit.assert_awaited_once()


@pytest.mark.parametrize("operation", ["update", "settings"])
async def test_streak_failure_prevents_flush_and_commit(
    profile, operation: str
) -> None:
    uow = make_uow()
    user = User(**profile.model_dump())
    user.streak_days = user.max_streak_days = 1
    user.last_streak_date = datetime.now(UTC).date() - timedelta(days=2)
    uow.users.get_by_id.return_value = user
    uow.activity.pending_days.side_effect = RuntimeError("activity lookup failed")
    service = UserService(lambda: uow, streak_factory=StreakService)
    with pytest.raises(RuntimeError, match="activity lookup failed"):
        if operation == "update":
            await service.update(user.id, UserProfileUpdateInput(first_name="After"))
        else:
            await service.replace_settings(
                user.id, UserSettingsReplaceInput(settings={"theme": "dark"})
            )
    uow.flush.assert_not_awaited()
    uow.commit.assert_not_awaited()
    assert uow.__aexit__.await_args.args[0] is RuntimeError
