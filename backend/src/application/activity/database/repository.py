from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from application.activity.database.models import UserDailyActivity
from application.study.database.models import StudySession

if TYPE_CHECKING:
    from datetime import date, datetime

    from sqlalchemy.ext.asyncio import AsyncSession


class SQLAActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def completed_days(self, user_id: int) -> set[date]:
        query = (
            select(UserDailyActivity.activity_date)
            .where(
                UserDailyActivity.user_id == user_id,
                UserDailyActivity.completed.is_(True),
            )
            .distinct()
        )
        return set((await self._session.scalars(query)).all())

    async def pending_days(self, user_id: int, now: datetime) -> set[date]:
        query = (
            select(StudySession.study_date)
            .where(
                StudySession.user_id == user_id,
                StudySession.status == "active",
                StudySession.expires_at > now,
            )
            .distinct()
        )
        return set((await self._session.scalars(query)).all())

    async def record_activity(self, user_id: int, day: date, completed: bool) -> None:
        statement = insert(UserDailyActivity).values(
            user_id=user_id, activity_date=day, cards_reviewed=1, completed=completed
        )
        statement = statement.on_conflict_do_update(
            index_elements=[UserDailyActivity.user_id, UserDailyActivity.activity_date],
            set_={
                "cards_reviewed": UserDailyActivity.cards_reviewed + 1,
                "completed": UserDailyActivity.completed | completed,
            },
        )
        await self._session.execute(statement)
