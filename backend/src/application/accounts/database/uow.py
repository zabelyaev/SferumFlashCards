from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType
    from typing import Self

    from application.accounts.users.contracts.inputs import UserSettingsReplaceInput
    from application.accounts.users.contracts.outputs import CurrentUserOutput
    from application.accounts.users.database.models import User
    from application.activity.database.uow import ActivityRepository


class UserRepository(Protocol):
    async def get_by_id(
        self,
        user_id: int,
        *,
        for_update: bool = False,
        no_key_update: bool = False,
    ) -> User: ...

    async def find_current_by_vk_id(
        self, vk_user_id: int
    ) -> CurrentUserOutput | None: ...

    async def find_by_vk_id(
        self, vk_user_id: int, *, no_key_update: bool = False
    ) -> User | None: ...

    async def list_page(self, *, page: int, limit: int) -> Sequence[User]: ...

    async def upsert_by_vk_id(
        self, vk_user_id: int, *, profile: dict[str, object]
    ) -> User: ...

    async def update(
        self,
        user: User,
        *,
        profile: dict[str, object],
    ) -> None: ...

    async def replace_settings(
        self, user: User, *, data: UserSettingsReplaceInput
    ) -> None: ...

    async def delete(self, user_id: int) -> None: ...


class AccountsUnitOfWork(Protocol):
    @property
    def users(self) -> UserRepository: ...

    @property
    def activity(self) -> ActivityRepository: ...
    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def flush(self) -> None: ...


class AccountsUnitOfWorkFactory(Protocol):
    def __call__(self) -> AccountsUnitOfWork: ...
