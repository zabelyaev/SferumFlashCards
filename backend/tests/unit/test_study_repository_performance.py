from datetime import date
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql

from application.study.contracts.types import DailyUsageCounts
from application.study.database.repository import StudyRepository


def sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


async def test_review_loads_only_unfinished_queue_without_snapshots() -> None:
    session = AsyncMock()
    session.scalars.return_value = MagicMock()
    session.scalars.return_value.all.return_value = []
    assert await StudyRepository(session).review_cards(5) == []
    compiled = sql(session.scalars.call_args.args[0])
    assert "snapshot" not in compiled
    assert "completed_at IS NULL" in compiled
    assert "fsrs_state" in compiled
    assert "source_card_id" in compiled
    assert (
        "ORDER BY study_session_cards.order_index, study_session_cards.id" in compiled
    )


async def test_session_lock_refreshes_existing_identity_map_state() -> None:
    session = AsyncMock()
    await StudyRepository(session).session(1, 5)
    statement = session.scalar.call_args.args[0]
    assert statement.get_execution_options()["populate_existing"] is True
    assert sql(statement).endswith("FOR UPDATE")


async def test_quota_reads_counters_without_scanning_logs_or_card_ids() -> None:
    session = AsyncMock()
    session.execute.return_value = MagicMock()
    session.execute.return_value.first.return_value = (3, 2)
    assert await StudyRepository(session).usage_counts(1, 2, date(2026, 11, 6)) == (
        DailyUsageCounts(3, 2)
    )
    compiled = sql(session.execute.call_args.args[0])
    assert "study_daily_usage" in compiled
    assert "review_logs" not in compiled
    assert "count(" not in compiled
    assert "card_id" not in compiled


async def test_missing_daily_quota_is_zero() -> None:
    session = AsyncMock()
    session.execute.return_value = MagicMock()
    session.execute.return_value.first.return_value = None
    assert await StudyRepository(session).usage_counts(1, 2, date(2026, 11, 6)) == (
        DailyUsageCounts(0, 0)
    )


async def test_quota_write_atomically_combines_unique_card_and_counters() -> None:
    session = AsyncMock()
    await StudyRepository(session).record_usage(
        1, 2, date(2026, 11, 6), 3, was_new=True
    )
    session.execute.assert_awaited_once()
    compiled = sql(session.execute.call_args.args[0])
    assert "WITH inserted_usage AS" in compiled
    assert "ON CONFLICT DO NOTHING" in compiled
    assert "promoted_usage AS" in compiled
    assert "INSERT INTO study_daily_usage" in compiled
    assert "DO UPDATE SET" in compiled
    assert "review_logs" not in compiled
