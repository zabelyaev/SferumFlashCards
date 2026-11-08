from typing import TYPE_CHECKING

from application.accounts.users.database.repository import SQLAUserRepository
from application.activity.database.repository import SQLAActivityRepository

if TYPE_CHECKING:
    from types import TracebackType
    from typing import Self

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from application.accounts.database.uow import AccountsUnitOfWork, UserRepository
    from application.activity.database.uow import ActivityRepository


class SQLAUnitOfWork:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.users: UserRepository
        self.activity: ActivityRepository

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.users = SQLAUserRepository(self._session)
        self.activity = SQLAActivityRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if session.in_transaction():
                await session.rollback()
        finally:
            await session.close()

    async def commit(self) -> None:
        await self._require_session().commit()

    async def flush(self) -> None:
        await self._require_session().flush()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Unit of Work has not been entered.")
        return self._session


class SQLAUnitOfWorkFactory:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    def __call__(self) -> AccountsUnitOfWork:
        return SQLAUnitOfWork(self._session_factory)
