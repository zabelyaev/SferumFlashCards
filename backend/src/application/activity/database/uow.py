from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import date, datetime

    from application.activity.service import StreakService


class ActivityRepository(Protocol):
    async def completed_days(self, user_id: int) -> set[date]: ...

    async def pending_days(self, user_id: int, now: datetime) -> set[date]: ...

    async def record_activity(
        self, user_id: int, day: date, completed: bool
    ) -> None: ...


class StreakServiceFactory(Protocol):
    def __call__(self, repo: ActivityRepository, /) -> StreakService: ...
