from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from application.accounts.users.contracts.outputs import CurrentUserOutput
from application.accounts.users.database.models import User
from common.exceptions.forbidden import ForbiddenError
from common.exceptions.not_found import NotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from application.accounts.users.contracts.inputs import UserSettingsReplaceInput


class SQLAUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self, user_id: int, *, for_update: bool = False, no_key_update: bool = False
    ) -> User:
        stmt = select(User).where(User.id == user_id)
        if no_key_update:
            stmt = stmt.with_for_update(of=User, key_share=True)
        elif for_update:
            stmt = stmt.with_for_update(of=User)
        user = (await self._session.execute(stmt)).scalar_one_or_none()
        if user is None:
            raise NotFoundError(f"User with id {user_id} not found.")
        return user

    async def find_current_by_vk_id(self, vk_user_id: int) -> CurrentUserOutput | None:
        stmt = select(User.id, User.is_active).where(User.vk_user_id == vk_user_id)
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            return None
        return CurrentUserOutput(id=row.id, is_active=row.is_active)

    async def find_by_vk_id(
        self, vk_user_id: int, *, no_key_update: bool = False
    ) -> User | None:
        stmt = select(User).where(User.vk_user_id == vk_user_id)
        if no_key_update:
            stmt = stmt.with_for_update(of=User, key_share=True)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_page(self, *, page: int, limit: int) -> Sequence[User]:
        stmt = select(User).order_by(User.id).offset(page * limit).limit(limit)
        return (await self._session.execute(stmt)).scalars().all()

    async def upsert_by_vk_id(
        self, vk_user_id: int, *, profile: dict[str, object]
    ) -> User:
        if not profile:
            user = await self.find_by_vk_id(vk_user_id, no_key_update=True)
            if user is not None:
                if not user.is_active:
                    raise ForbiddenError("User is disabled.")
                return user

        stmt = insert(User).values(vk_user_id=vk_user_id, **profile)
        changes = (
            {**profile, "updated_at": func.now()}
            if profile
            else {"vk_user_id": stmt.excluded.vk_user_id}
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[User.vk_user_id],
            set_=changes,
            where=User.is_active.is_(True),
        ).returning(User)
        user = (await self._session.execute(stmt)).scalar_one_or_none()
        if user is None:
            raise ForbiddenError("User is disabled.")
        return user

    async def update(self, user: User, *, profile: dict[str, object]) -> None:
        if not user.is_active:
            raise ForbiddenError("User is disabled.")
        for field, value in profile.items():
            setattr(user, field, value)

    async def replace_settings(
        self, user: User, *, data: UserSettingsReplaceInput
    ) -> None:
        if not user.is_active:
            raise ForbiddenError("User is disabled.")
        user.settings = dict(data.settings)

    async def delete(self, user_id: int) -> None:
        await self._session.delete(await self.get_by_id(user_id, for_update=True))
