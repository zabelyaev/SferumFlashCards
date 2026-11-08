from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from application.accounts.users.contracts.mappers import to_user_profile_output
from common.exceptions.forbidden import ForbiddenError
from common.exceptions.unauthorized import UnauthorizedError

if TYPE_CHECKING:
    from application.accounts.database.uow import AccountsUnitOfWorkFactory
    from application.accounts.users.contracts.inputs import (
        UserProfileUpdateInput,
        UserSettingsReplaceInput,
        UserSyncInput,
    )
    from application.accounts.users.contracts.outputs import (
        CurrentUserOutput,
        UserProfileOutput,
    )
    from application.activity.database.uow import StreakServiceFactory


class UserService:
    def __init__(
        self,
        uow_factory: AccountsUnitOfWorkFactory,
        streak_factory: StreakServiceFactory,
    ) -> None:
        self._uow_factory = uow_factory
        self._streak_factory = streak_factory

    async def get_current(self, vk_user_id: int) -> CurrentUserOutput:
        async with self._uow_factory() as uow:
            user = await uow.users.find_current_by_vk_id(vk_user_id)
            if user is None:
                raise UnauthorizedError("Synchronize the user first.")
            if not user.is_active:
                raise ForbiddenError("User is disabled.")
            return user

    async def get_profile(self, user_id: int) -> UserProfileOutput:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id, no_key_update=True)
            streaks = self._streak_factory(uow.activity)
            await streaks.ensure_current(user, datetime.now(UTC))
            await uow.flush()
            result = to_user_profile_output(user)
            await uow.commit()
            return result

    async def sync(self, model: UserSyncInput) -> UserProfileOutput:
        profile = model.model_dump(
            mode="json", exclude_unset=True, exclude={"vk_user_id"}
        )
        async with self._uow_factory() as uow:
            user = await uow.users.upsert_by_vk_id(model.vk_user_id, profile=profile)
            streaks = self._streak_factory(uow.activity)
            now = datetime.now(UTC)
            if "timezone" in profile:
                await streaks.recalculate(user, now)
            else:
                await streaks.ensure_current(user, now)
            await uow.flush()
            result = to_user_profile_output(user)
            await uow.commit()
            return result

    async def update(
        self, user_id: int, model: UserProfileUpdateInput
    ) -> UserProfileOutput:
        async with self._uow_factory() as uow:
            profile = model.model_dump(mode="json", exclude_unset=True)
            user = await uow.users.get_by_id(user_id, no_key_update=True)
            previous_timezone = user.timezone
            await uow.users.update(user, profile=profile)
            streaks = self._streak_factory(uow.activity)
            now = datetime.now(UTC)
            if user.timezone != previous_timezone:
                await streaks.recalculate(user, now)
            else:
                await streaks.ensure_current(user, now)
            await uow.flush()
            result = to_user_profile_output(user)
            await uow.commit()
            return result

    async def replace_settings(
        self, user_id: int, model: UserSettingsReplaceInput
    ) -> UserProfileOutput:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id, no_key_update=True)
            await uow.users.replace_settings(user, data=model)
            streaks = self._streak_factory(uow.activity)
            await streaks.ensure_current(user, datetime.now(UTC))
            await uow.flush()
            result = to_user_profile_output(user)
            await uow.commit()
            return result

    async def delete(self, user_id: int) -> None:
        async with self._uow_factory() as uow:
            await uow.users.delete(user_id)
            await uow.commit()
