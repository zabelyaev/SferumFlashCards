from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from application.accounts.users.database.models import User
from application.study.contracts.types import DailyUsage, DailyUsageCounts
from application.study.database.models import StudyDailyCard, StudyDailyUsage
from application.study.database.repository import StudyRepository
from common.database import DatabaseHelper

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration
DAY = date(2026, 11, 6)


@pytest_asyncio.fixture
async def usage_session(
    validated_test_database,
) -> AsyncIterator[tuple[AsyncSession, int]]:
    helper = DatabaseHelper(validated_test_database)
    try:
        async with helper.session_factory() as session, session.begin():
            user = User(vk_user_id=96273295)
            session.add(user)
            await session.flush()
            yield session, user.id
            await session.rollback()
    finally:
        await helper.dispose()


async def test_unique_daily_usage_and_new_flag_promotion(usage_session) -> None:
    session, user_id = usage_session
    repo = StudyRepository(session)
    assert await repo.usage_counts(user_id, 7, DAY) == DailyUsageCounts(0, 0)

    await repo.record_usage(user_id, 7, DAY, 9, was_new=False)
    assert await repo.usage_counts(user_id, 7, DAY) == DailyUsageCounts(1, 0)
    for _ in range(10):
        await repo.record_usage(user_id, 7, DAY, 9, was_new=False)
    assert await repo.usage_counts(user_id, 7, DAY) == DailyUsageCounts(1, 0)

    await repo.record_usage(user_id, 7, DAY, 9, was_new=True)
    await repo.record_usage(user_id, 7, DAY, 9, was_new=True)
    await repo.record_usage(user_id, 7, DAY, 9, was_new=False)
    assert await repo.usage_counts(user_id, 7, DAY) == DailyUsageCounts(1, 1)
    await repo.record_usage(user_id, 7, DAY, 10, was_new=True)
    assert await repo.usage_counts(user_id, 7, DAY) == DailyUsageCounts(2, 2)
    assert await repo.used(user_id, 7, DAY) == DailyUsage(
        frozenset({9, 10}), frozenset({9, 10})
    )
    assert await session.scalar(select(func.count()).select_from(StudyDailyCard)) == 2


async def test_daily_usage_is_separate_per_day_deck_and_user(usage_session) -> None:
    session, user_id = usage_session
    other = User(vk_user_id=96273296)
    session.add(other)
    await session.flush()
    repo = StudyRepository(session)
    await repo.record_usage(user_id, 7, DAY, 9, was_new=True)
    await repo.record_usage(user_id, 8, DAY, 9, was_new=False)
    await repo.record_usage(user_id, 7, DAY + timedelta(days=1), 9, was_new=False)
    await repo.record_usage(other.id, 7, DAY, 9, was_new=False)
    assert await repo.usage_counts(user_id, 7, DAY) == DailyUsageCounts(1, 1)
    assert await repo.usage_counts(user_id, 8, DAY) == DailyUsageCounts(1, 0)
    assert await repo.usage_counts(user_id, 7, DAY + timedelta(days=1)) == (
        DailyUsageCounts(1, 0)
    )
    assert await repo.usage_counts(other.id, 7, DAY) == DailyUsageCounts(1, 0)


async def test_daily_usage_rolls_back_both_unique_card_and_counters(
    usage_session,
) -> None:
    session, user_id = usage_session
    repo = StudyRepository(session)
    await repo.record_usage(user_id, 7, DAY, 9, was_new=False)
    transaction = await session.begin_nested()
    await repo.record_usage(user_id, 7, DAY, 9, was_new=True)
    await repo.record_usage(user_id, 7, DAY, 10, was_new=True)
    await transaction.rollback()
    assert await repo.usage_counts(user_id, 7, DAY) == DailyUsageCounts(1, 0)
    assert await repo.used(user_id, 7, DAY) == DailyUsage(frozenset({9}), frozenset())


async def test_repeated_usage_does_not_rewrite_counter_row(usage_session) -> None:
    from sqlalchemy import text

    session, user_id = usage_session
    repo = StudyRepository(session)
    await repo.record_usage(user_id, 7, DAY, 9, was_new=True)
    before = await session.scalar(text("SELECT ctid::text FROM study_daily_usage"))
    await repo.record_usage(user_id, 7, DAY, 9, was_new=False)
    await repo.record_usage(user_id, 7, DAY, 9, was_new=True)
    after = await session.scalar(text("SELECT ctid::text FROM study_daily_usage"))
    assert before == after
    assert await session.scalar(select(func.count()).select_from(StudyDailyUsage)) == 1
