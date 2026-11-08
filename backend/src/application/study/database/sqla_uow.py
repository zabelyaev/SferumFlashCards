from typing import TYPE_CHECKING

from application.accounts.users.database.repository import SQLAUserRepository
from application.activity.database.repository import SQLAActivityRepository
from application.study.database.repository import StudyRepository

if TYPE_CHECKING:
    from types import TracebackType
    from typing import Self

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from application.accounts.database.uow import UserRepository
    from application.activity.database.uow import ActivityRepository


class SQLAStudyUnitOfWork:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    async def __aenter__(self) -> Self:
        self.session = self.factory()
        self.repo = StudyRepository(self.session)
        self.activity: ActivityRepository = SQLAActivityRepository(self.session)
        self.users: UserRepository = SQLAUserRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if self.session.in_transaction():
                await self.session.rollback()
        finally:
            await self.session.close()

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()


class SQLAStudyUnitOfWorkFactory:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    def __call__(self) -> SQLAStudyUnitOfWork:
        return SQLAStudyUnitOfWork(self.factory)
