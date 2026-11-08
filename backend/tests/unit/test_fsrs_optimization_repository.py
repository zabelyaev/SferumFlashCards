from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fsrs.scheduler import DEFAULT_PARAMETERS
from sqlalchemy.dialects import postgresql

from application.study.optimization.repository import (
    OptimizationLock,
    OptimizationRepository,
)
from common.config.study import StudyConfig


def connection_and_repository():
    connection = MagicMock()
    connection.execute = AsyncMock(return_value=MagicMock())
    connection.execution_options = AsyncMock(return_value=connection)
    connection.scalars = AsyncMock(return_value=MagicMock())
    engine = MagicMock()
    engine.connect.return_value.__aenter__.return_value = connection
    return connection, OptimizationRepository(engine)


async def test_history_selects_compact_compatibility_in_repeatable_read() -> None:
    connection, repository = connection_and_repository()
    user_result = MagicMock()
    user_result.first.return_value = SimpleNamespace(fsrs_parameters=None)
    review_result = MagicMock()
    review_result.all.return_value = []
    connection.execute.side_effect = [user_result, review_result]
    config = StudyConfig(learning_step_seconds=120, relearning_step_seconds=700)
    history = await repository.history(OptimizationLock(connection, 17), 7, config)
    assert history is not None and history.reviews == ()
    connection.execution_options.assert_awaited_once_with(
        isolation_level="REPEATABLE READ"
    )
    connection.begin.assert_called_once_with()
    statement = connection.execute.await_args_list[1].args[0]
    assert list(statement.selected_columns.keys()) == [
        "id",
        "cycle_id",
        "rating",
        "reviewed_at",
        "compatible",
    ]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "coalesce(" in sql and "jsonb_typeof(" in sql
    assert sql.count("jsonb_extract_path(") == 3
    assert "library_version" in compiled.params.values()
    assert version("fsrs") in compiled.params.values()
    assert "learning_steps" in compiled.params.values()
    assert "relearning_steps" in compiled.params.values()
    assert [120] in compiled.params.values()
    assert [700] in compiled.params.values()
    assert "review_logs.cycle_id IS NOT NULL" in sql
    assert "review_logs.user_id =" in sql
    assert "ORDER BY review_logs.reviewed_at, review_logs.id" in sql


async def test_history_excludes_all_reviews_of_any_incompatible_cycle() -> None:
    connection, repository = connection_and_repository()
    user_result = MagicMock()
    user_result.first.return_value = SimpleNamespace(
        fsrs_parameters=list(DEFAULT_PARAMETERS)
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        SimpleNamespace(
            id=index,
            cycle_id=cycle,
            rating=3,
            reviewed_at=start + timedelta(days=index),
            compatible=compatible,
        )
        for index, (cycle, compatible) in enumerate(
            [(1, True), (2, True), (1, False), (3, True), (2, None), (1, True)],
            start=1,
        )
    ]
    review_result = MagicMock()
    review_result.all.return_value = rows
    connection.execute.side_effect = [user_result, review_result]
    history = await repository.history(
        OptimizationLock(connection, 17), 7, StudyConfig()
    )
    assert history is not None
    assert history.parameters == tuple(DEFAULT_PARAMETERS)
    assert history.incompatible_cycles == 2
    assert [(review.cycle_id, review.review_id) for review in history.reviews] == [
        (3, 4)
    ]


async def test_history_does_not_read_reviews_of_missing_or_disabled_user() -> None:
    connection, repository = connection_and_repository()
    connection.execute.return_value.first.return_value = None
    assert (
        await repository.history(OptimizationLock(connection, 17), 7, StudyConfig())
        is None
    )
    connection.execute.assert_awaited_once()
    sql = str(
        connection.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    )
    assert "users.is_active IS true" in sql


@pytest.mark.parametrize("ids", [[], [7, 11]])
async def test_eligible_users_uses_bounded_existence_and_keyset(ids) -> None:
    connection, repository = connection_and_repository()
    connection.scalars.return_value.all.return_value = ids
    assert await repository.eligible_users(after_id=5, limit=23) == ids
    statement = connection.scalars.await_args.args[0]
    sql = " ".join(
        str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        ).split()
    )
    assert "users.id > 5" in sql
    assert "users.is_active IS true" in sql
    assert "EXISTS (SELECT review_logs.id FROM review_logs" in sql
    assert "review_logs.user_id = users.id" in sql
    assert "review_logs.cycle_id IS NOT NULL" in sql
    assert "LIMIT 1 OFFSET 513" in sql
    assert "ORDER BY users.id LIMIT 23" in sql
    assert "count(" not in sql.lower()
    assert "GROUP BY" not in sql and "HAVING" not in sql
