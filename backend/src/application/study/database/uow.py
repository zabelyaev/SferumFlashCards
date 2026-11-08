from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from types import TracebackType
    from typing import Self

    from application.accounts.database.uow import UserRepository
    from application.activity.database.uow import ActivityRepository
    from application.study.database.repository import StudyRepository


class StudyUnitOfWork(Protocol):
    repo: StudyRepository
    activity: ActivityRepository
    users: UserRepository

    async def __aenter__(self) -> Self: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
    async def flush(self) -> None: ...
    async def commit(self) -> None: ...


type StudyUnitOfWorkFactory = Callable[[], StudyUnitOfWork]
