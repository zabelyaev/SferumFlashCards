from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from application.activity.contracts.outputs import StreakResult

if TYPE_CHECKING:
    from datetime import date, datetime

    from application.accounts.users.database.models import User
    from application.activity.database.uow import ActivityRepository


class StreakService:
    def __init__(self, repo: ActivityRepository) -> None:
        self._repo = repo

    async def ensure_current(self, user: User, now: datetime) -> None:
        last = user.last_streak_date
        if last is None or user.streak_days == 0:
            return
        today = now.astimezone(ZoneInfo(user.timezone)).date()
        if (today - last).days <= 1:
            return
        pending = await self._repo.pending_days(user.id, now)
        if self._has_final_missed_day(last, pending, today):
            user.streak_days = 0

    async def recalculate(self, user: User, now: datetime) -> None:
        completed = await self._repo.completed_days(user.id)
        pending = await self._repo.pending_days(user.id, now) if completed else set()
        result = self._calculate_streak(
            completed,
            pending,
            now.astimezone(ZoneInfo(user.timezone)).date(),
            user.max_streak_days,
        )
        user.streak_days = result.streak_days
        user.max_streak_days = result.max_streak_days
        user.last_streak_date = result.last_streak_date

    @staticmethod
    def _has_final_missed_day(
        last_streak_date: date, pending_days: set[date], today: date
    ) -> bool:
        gap_days = (today - last_streak_date).days - 1
        pending_gap_days = sum(last_streak_date < day < today for day in pending_days)
        return gap_days > pending_gap_days

    @staticmethod
    def _calculate_streak(
        completed_days: set[date],
        pending_days: set[date],
        today: date,
        max_streak_days: int,
    ) -> StreakResult:
        days = sorted(completed_days)
        if not days:
            return StreakResult(0, max_streak_days, None)

        best = run = 1
        for previous, current in zip(days, days[1:]):
            run = run + 1 if current - previous == timedelta(days=1) else 1
            best = max(best, run)

        last = days[-1]
        if StreakService._has_final_missed_day(last, pending_days, today):
            run = 0
        return StreakResult(run, max(max_streak_days, best), last)
