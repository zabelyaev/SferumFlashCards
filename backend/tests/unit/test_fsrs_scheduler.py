import asyncio
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from cli import fsrs_scheduler


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (
            datetime(2026, 1, 1, 20, 59, tzinfo=UTC),
            datetime(2026, 1, 1, 21, tzinfo=UTC),
        ),
        (datetime(2026, 1, 1, 21, tzinfo=UTC), datetime(2026, 1, 2, 21, tzinfo=UTC)),
        (datetime(2026, 12, 31, 23, tzinfo=UTC), datetime(2027, 1, 1, 21, tzinfo=UTC)),
        (
            datetime(2026, 1, 1, 23, tzinfo=timezone(timedelta(hours=3))),
            datetime(2026, 1, 1, 21, tzinfo=UTC),
        ),
    ],
)
def test_next_run_is_strictly_after_current_time_in_utc(now, expected) -> None:
    assert fsrs_scheduler.next_run(now, 21) == expected


def test_next_run_rejects_naive_clock() -> None:
    with pytest.raises(ValueError):
        fsrs_scheduler.next_run(datetime(2026, 1, 1), 21)


@pytest.mark.parametrize("value", ["-1", "24", "noon", "1.5", ""])
def test_invalid_hour_is_rejected(monkeypatch, value) -> None:
    monkeypatch.setenv("FSRS_OPTIMIZER_HOUR_UTC", value)
    with pytest.raises(ValueError, match="FSRS_OPTIMIZER_HOUR_UTC"):
        fsrs_scheduler.configured_hour()


def test_default_and_configured_hour(monkeypatch) -> None:
    monkeypatch.delenv("FSRS_OPTIMIZER_HOUR_UTC", raising=False)
    assert fsrs_scheduler.configured_hour() == 21
    monkeypatch.setenv("FSRS_OPTIMIZER_HOUR_UTC", "0")
    assert fsrs_scheduler.configured_hour() == 0
    monkeypatch.setenv("FSRS_OPTIMIZER_HOUR_UTC", "23")
    assert fsrs_scheduler.configured_hour() == 23


@pytest.mark.parametrize(
    ("clock", "hour", "expected"),
    [
        (
            datetime(2026, 1, 1, 20, tzinfo=UTC),
            21,
            datetime(2026, 1, 1, 21, tzinfo=UTC),
        ),
        (
            datetime(2026, 1, 1, 21, tzinfo=UTC),
            21,
            datetime(2026, 1, 2, 21, tzinfo=UTC),
        ),
        (
            datetime(2026, 1, 1, 21, 0, 30, tzinfo=UTC),
            21,
            datetime(2026, 1, 2, 21, tzinfo=UTC),
        ),
        (
            datetime(2026, 1, 1, 21, 30, tzinfo=UTC),
            21,
            datetime(2026, 1, 2, 21, tzinfo=UTC),
        ),
        (datetime(2026, 1, 1, 4, tzinfo=UTC), 5, datetime(2026, 1, 1, 5, tzinfo=UTC)),
        (datetime(2026, 1, 1, 6, tzinfo=UTC), 5, datetime(2026, 1, 2, 5, tzinfo=UTC)),
    ],
)
async def test_startup_waits_without_running_batch(
    monkeypatch, capsys, clock, hour, expected
) -> None:

    class Clock:
        @staticmethod
        def now(tz):
            assert tz == UTC
            return clock

    batch = AsyncMock(return_value=0)
    wait = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(fsrs_scheduler, "datetime", Clock)
    monkeypatch.setattr(fsrs_scheduler, "run", batch)
    monkeypatch.setattr(fsrs_scheduler, "wait_until", wait)
    with pytest.raises(asyncio.CancelledError):
        await fsrs_scheduler.schedule(hour)
    batch.assert_not_awaited()
    wait.assert_awaited_once_with(expected)
    output = capsys.readouterr().out
    assert '"next_batch"' in output
    assert '"batch_started"' not in output


async def test_error_waits_for_next_daily_slot(monkeypatch, capsys) -> None:
    class Clock:
        current = datetime(2026, 1, 1, 20, tzinfo=UTC)

        @staticmethod
        def now(tz):
            return Clock.current

    async def wait_for_slot(target):
        if wait.await_count == 1:
            batch.assert_not_awaited()
            Clock.current = target
        else:
            raise asyncio.CancelledError

    batch = AsyncMock(side_effect=OSError("DB down"))
    wait = AsyncMock(side_effect=wait_for_slot)
    monkeypatch.setattr(fsrs_scheduler, "datetime", Clock)
    monkeypatch.setattr(fsrs_scheduler, "run", batch)
    monkeypatch.setattr(fsrs_scheduler, "wait_until", wait)
    with pytest.raises(asyncio.CancelledError):
        await fsrs_scheduler.schedule(21)
    batch.assert_awaited_once_with(None)
    assert [call.args[0] for call in wait.await_args_list] == [
        datetime(2026, 1, 1, 21, tzinfo=UTC),
        datetime(2026, 1, 2, 21, tzinfo=UTC),
    ]
    assert '"batch_failed"' in capsys.readouterr().out


async def test_each_batch_waits_for_its_daily_slot(monkeypatch) -> None:
    class Clock:
        current = datetime(2026, 1, 1, 20, tzinfo=UTC)

        @staticmethod
        def now(tz):
            return Clock.current

    async def wait_for_slot(target):
        assert batch.await_count == wait.await_count - 1
        if wait.await_count == 3:
            raise asyncio.CancelledError
        Clock.current = target

    batch = AsyncMock(side_effect=[1, 0])
    wait = AsyncMock(side_effect=wait_for_slot)
    monkeypatch.setattr(fsrs_scheduler, "datetime", Clock)
    monkeypatch.setattr(fsrs_scheduler, "run", batch)
    monkeypatch.setattr(fsrs_scheduler, "wait_until", wait)
    with pytest.raises(asyncio.CancelledError):
        await fsrs_scheduler.schedule(21)
    assert batch.await_count == 2
    assert [call.args[0] for call in wait.await_args_list] == [
        datetime(2026, 1, 1, 21, tzinfo=UTC),
        datetime(2026, 1, 2, 21, tzinfo=UTC),
        datetime(2026, 1, 3, 21, tzinfo=UTC),
    ]


async def test_long_batch_skips_missed_slots_without_catchup(monkeypatch) -> None:
    class Clock:
        current = datetime(2026, 1, 1, 20, tzinfo=UTC)

        @staticmethod
        def now(tz):
            return Clock.current

    async def wait_for_slot(target):
        if wait.await_count == 1:
            Clock.current = target
        else:
            raise asyncio.CancelledError

    async def long_batch(user_id):
        assert Clock.current == datetime(2026, 1, 1, 21, tzinfo=UTC)
        Clock.current = datetime(2026, 1, 3, 21, 30, tzinfo=UTC)
        return 0

    batch = AsyncMock(side_effect=long_batch)
    wait = AsyncMock(side_effect=wait_for_slot)
    monkeypatch.setattr(fsrs_scheduler, "datetime", Clock)
    monkeypatch.setattr(fsrs_scheduler, "run", batch)
    monkeypatch.setattr(fsrs_scheduler, "wait_until", wait)
    with pytest.raises(asyncio.CancelledError):
        await fsrs_scheduler.schedule(21)
    batch.assert_awaited_once_with(None)
    assert [call.args[0] for call in wait.await_args_list] == [
        datetime(2026, 1, 1, 21, tzinfo=UTC),
        datetime(2026, 1, 4, 21, tzinfo=UTC),
    ]


@pytest.mark.parametrize(
    "delay", [timedelta(seconds=61), timedelta(days=2, minutes=30)]
)
async def test_late_wakeup_skips_slot_and_waits_for_next_utc_hour(
    monkeypatch, capsys, delay
) -> None:
    class Clock:
        current = datetime(2026, 1, 1, 20, tzinfo=UTC)

        @staticmethod
        def now(tz):
            assert tz == UTC
            return Clock.current

    async def wait_for_slot(target):
        if wait.await_count == 1:
            Clock.current = target + delay
        elif wait.await_count == 2:
            batch.assert_not_awaited()
            Clock.current = target
        else:
            raise asyncio.CancelledError

    batch = AsyncMock(return_value=0)
    wait = AsyncMock(side_effect=wait_for_slot)
    monkeypatch.setattr(fsrs_scheduler, "datetime", Clock)
    monkeypatch.setattr(fsrs_scheduler, "run", batch)
    monkeypatch.setattr(fsrs_scheduler, "wait_until", wait)
    first = datetime(2026, 1, 1, 21, tzinfo=UTC)
    second = fsrs_scheduler.next_run(first + delay, 21)
    with pytest.raises(asyncio.CancelledError):
        await fsrs_scheduler.schedule(21)
    batch.assert_awaited_once_with(None)
    assert [call.args[0] for call in wait.await_args_list] == [
        first,
        second,
        second + timedelta(days=1),
    ]
    output = capsys.readouterr().out
    assert output.count('"batch_skipped"') == 1
    assert '"missed_slot"' in output
    assert output.count('"batch_started"') == 1


@pytest.mark.parametrize("delay_seconds", [0, 30, 60])
async def test_small_wakeup_delay_can_run_only_the_scheduled_slot(
    monkeypatch, delay_seconds
) -> None:
    class Clock:
        current = datetime(2026, 1, 1, 20, tzinfo=UTC)

        @staticmethod
        def now(tz):
            return Clock.current

    async def wait_for_slot(target):
        if wait.await_count == 1:
            batch.assert_not_awaited()
            Clock.current = target + timedelta(seconds=delay_seconds)
        else:
            raise asyncio.CancelledError

    batch = AsyncMock(return_value=0)
    wait = AsyncMock(side_effect=wait_for_slot)
    monkeypatch.setattr(fsrs_scheduler, "datetime", Clock)
    monkeypatch.setattr(fsrs_scheduler, "run", batch)
    monkeypatch.setattr(fsrs_scheduler, "wait_until", wait)
    with pytest.raises(asyncio.CancelledError):
        await fsrs_scheduler.schedule(21)
    batch.assert_awaited_once_with(None)
    assert [call.args[0] for call in wait.await_args_list] == [
        datetime(2026, 1, 1, 21, tzinfo=UTC),
        datetime(2026, 1, 2, 21, tzinfo=UTC),
    ]


async def test_clock_rollback_after_wait_does_not_start_batch_early(
    monkeypatch,
) -> None:
    class Clock:
        current = datetime(2026, 1, 1, 20, tzinfo=UTC)

        @staticmethod
        def now(tz):
            return Clock.current

    async def wait_for_slot(target):
        if wait.await_count == 1:
            Clock.current = target - timedelta(seconds=1)
        elif wait.await_count == 2:
            batch.assert_not_awaited()
            Clock.current = target
        else:
            raise asyncio.CancelledError

    batch = AsyncMock(return_value=0)
    wait = AsyncMock(side_effect=wait_for_slot)
    monkeypatch.setattr(fsrs_scheduler, "datetime", Clock)
    monkeypatch.setattr(fsrs_scheduler, "run", batch)
    monkeypatch.setattr(fsrs_scheduler, "wait_until", wait)
    with pytest.raises(asyncio.CancelledError):
        await fsrs_scheduler.schedule(21)
    batch.assert_awaited_once_with(None)
    assert [call.args[0] for call in wait.await_args_list] == [
        datetime(2026, 1, 1, 21, tzinfo=UTC),
        datetime(2026, 1, 1, 21, tzinfo=UTC),
        datetime(2026, 1, 2, 21, tzinfo=UTC),
    ]


async def test_stop_cancels_batch_and_waits_for_cleanup(monkeypatch) -> None:
    started = asyncio.Event()
    cleaned = asyncio.Event()

    async def batch(user_id):
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    class Clock:
        current = datetime(2026, 1, 1, 20, tzinfo=UTC)

        @staticmethod
        def now(tz):
            return Clock.current

    async def wait_for_slot(target):
        Clock.current = target

    monkeypatch.setattr(fsrs_scheduler, "datetime", Clock)
    monkeypatch.setattr(fsrs_scheduler, "run", batch)
    monkeypatch.setattr(fsrs_scheduler, "wait_until", wait_for_slot)
    task = asyncio.create_task(fsrs_scheduler.schedule(21))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()


async def test_cancelled_training_terminates_worker(monkeypatch) -> None:
    from application.study.optimization.engine import FsrsOptimizer
    from common.config.study import StudyConfig

    started = asyncio.Event()
    process = AsyncMock()
    process.returncode = None
    process.kill = lambda: None
    killed = False

    def kill():
        nonlocal killed
        killed = True

    async def communicate(payload):
        started.set()
        await asyncio.Event().wait()

    process.kill = kill
    process.communicate = communicate
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    task = asyncio.create_task(FsrsOptimizer().optimize([], StudyConfig()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert killed
    process.wait.assert_awaited_once()


async def test_wait_rechecks_wall_clock(monkeypatch) -> None:
    times = iter(
        [datetime(2026, 1, 1, 20, 58, tzinfo=UTC), datetime(2026, 1, 1, 21, tzinfo=UTC)]
    )

    class Clock:
        @staticmethod
        def now(tz):
            return next(times)

    sleep = AsyncMock()
    monkeypatch.setattr(fsrs_scheduler, "datetime", Clock)
    monkeypatch.setattr(fsrs_scheduler.asyncio, "sleep", sleep)
    await fsrs_scheduler.wait_until(datetime(2026, 1, 1, 21, tzinfo=UTC))
    sleep.assert_awaited_once_with(60)
