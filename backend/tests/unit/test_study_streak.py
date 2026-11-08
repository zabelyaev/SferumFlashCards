from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from application.accounts.users.database.models import User
from application.activity.service import StreakService


async def test_streak_waits_for_open_previous_day_and_keeps_record() -> None:
    user = User(id=1, vk_user_id=123, timezone="UTC", max_streak_days=5)
    repo = AsyncMock()
    repo.completed_days.return_value = {date(2026, 10, 31), date(2026, 11, 1)}
    repo.pending_days.return_value = {date(2026, 11, 2)}
    service = StreakService(repo)
    now = datetime(2026, 11, 3, tzinfo=UTC)
    await service.recalculate(user, now)
    assert (user.streak_days, user.max_streak_days, user.last_streak_date) == (
        2,
        5,
        date(2026, 11, 1),
    )
    repo.pending_days.return_value = set()
    await service.recalculate(user, now)
    assert (user.streak_days, user.max_streak_days, user.last_streak_date) == (
        0,
        5,
        date(2026, 11, 1),
    )


async def test_streak_reconciles_late_day_completion_in_date_order() -> None:
    user = User(id=1, vk_user_id=123, timezone="UTC", max_streak_days=1)
    repo = AsyncMock()
    repo.completed_days.return_value = {date(2026, 11, 1), date(2026, 11, 3)}
    repo.pending_days.return_value = {date(2026, 11, 2)}
    service = StreakService(repo)
    now = datetime(2026, 11, 3, tzinfo=UTC)
    await service.recalculate(user, now)
    assert user.streak_days == 1
    repo.completed_days.return_value.add(date(2026, 11, 2))
    repo.pending_days.return_value = set()
    await service.recalculate(user, now)
    assert (user.streak_days, user.max_streak_days, user.last_streak_date) == (
        3,
        3,
        date(2026, 11, 3),
    )


async def test_recalculate_streak_uses_local_date_and_updates_user() -> None:
    user = User(id=1, vk_user_id=123, timezone="Europe/Moscow", max_streak_days=5)
    repo = AsyncMock()
    repo.completed_days.return_value = {date(2026, 11, 1)}
    repo.pending_days.return_value = set()
    now = datetime(2026, 11, 2, 22, tzinfo=UTC)
    await StreakService(repo).recalculate(user, now)
    repo.completed_days.assert_awaited_once_with(1)
    repo.pending_days.assert_awaited_once_with(1, now)
    assert (user.streak_days, user.max_streak_days, user.last_streak_date) == (
        0,
        5,
        date(2026, 11, 1),
    )
    repo.commit.assert_not_called()


async def test_recalculate_streak_without_history_skips_pending_query() -> None:
    user = User(id=1, vk_user_id=123, timezone="UTC", max_streak_days=5)
    repo = AsyncMock()
    repo.completed_days.return_value = set()
    await StreakService(repo).recalculate(user, datetime(2026, 11, 3, tzinfo=UTC))
    repo.pending_days.assert_not_awaited()
    assert (user.streak_days, user.max_streak_days, user.last_streak_date) == (
        0,
        5,
        None,
    )


@pytest.mark.parametrize(
    ("last", "streak"),
    [
        (None, 0),
        (date(2026, 10, 1), 0),
        (date(2026, 11, 2), 2),
        (date(2026, 11, 3), 2),
        (date(2026, 11, 4), 2),
    ],
)
async def test_current_streak_skips_all_activity_queries(last, streak) -> None:
    user = User(
        id=1,
        vk_user_id=123,
        timezone="UTC",
        streak_days=streak,
        max_streak_days=5,
        last_streak_date=last,
    )
    repo = AsyncMock()
    await StreakService(repo).ensure_current(user, datetime(2026, 11, 3, tzinfo=UTC))
    repo.completed_days.assert_not_awaited()
    repo.pending_days.assert_not_awaited()
    assert (user.streak_days, user.max_streak_days, user.last_streak_date) == (
        streak,
        5,
        last,
    )


async def test_ensure_streak_waits_then_resets_after_pending_expires() -> None:
    user = User(
        id=1,
        vk_user_id=123,
        timezone="Europe/Moscow",
        streak_days=2,
        max_streak_days=5,
        last_streak_date=date(2026, 11, 1),
    )
    repo = AsyncMock()
    repo.pending_days.return_value = {date(2026, 11, 2)}
    now = datetime(2026, 11, 2, 22, tzinfo=UTC)
    service = StreakService(repo)
    await service.ensure_current(user, now)
    assert user.streak_days == 2
    repo.pending_days.return_value = set()
    await service.ensure_current(user, now)
    assert (user.streak_days, user.max_streak_days, user.last_streak_date) == (
        0,
        5,
        date(2026, 11, 1),
    )
    assert repo.pending_days.await_count == 2
    repo.completed_days.assert_not_awaited()
    await service.ensure_current(user, now)
    assert repo.pending_days.await_count == 2


@pytest.mark.parametrize(
    ("pending", "expected"),
    [
        ({date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 4)}, 0),
        ({date(2026, 11, 2), date(2026, 11, 3)}, 2),
    ],
)
async def test_pending_dates_outside_gap_do_not_prevent_reset(
    pending, expected
) -> None:
    user = User(
        id=1,
        vk_user_id=123,
        timezone="UTC",
        streak_days=2,
        max_streak_days=5,
        last_streak_date=date(2026, 11, 1),
    )
    repo = AsyncMock()
    repo.pending_days.return_value = pending
    await StreakService(repo).ensure_current(user, datetime(2026, 11, 4, tzinfo=UTC))
    assert user.streak_days == expected
    assert user.max_streak_days == 5
    repo.completed_days.assert_not_awaited()
