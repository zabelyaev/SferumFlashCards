"""Initial-schema checks use rollback-only schemas and a DDL-capable test role."""

import secrets
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import BigInteger, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import CreateSchema

import application.models  # noqa: F401
from common.database import Base

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.engine import Connection
    from sqlalchemy.ext.asyncio import AsyncConnection

pytestmark = pytest.mark.integration


def run_initial(connection: Connection, *, downgrade: bool = False) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "src" / "alembic.ini"))
    script = ScriptDirectory.from_config(config).get_revision("0001")
    assert script is not None
    context = MigrationContext.configure(
        connection, opts={"target_metadata": Base.metadata}
    )
    with Operations.context(context):
        if downgrade:
            script.module.downgrade()
        else:
            script.module.upgrade()


def run_activity_index_migration(connection: Connection, *, downgrade: bool) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "src" / "alembic.ini"))
    script = ScriptDirectory.from_config(config).get_revision("0002")
    assert script is not None
    context = MigrationContext.configure(
        connection, opts={"target_metadata": Base.metadata}
    )
    with Operations.context(context):
        if downgrade:
            script.module.downgrade()
        else:
            script.module.upgrade()


def run_nullable_deck_migration(connection: Connection, *, downgrade: bool) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "src" / "alembic.ini"))
    script = ScriptDirectory.from_config(config).get_revision("0003")
    assert script is not None
    context = MigrationContext.configure(
        connection, opts={"target_metadata": Base.metadata}
    )
    with Operations.context(context):
        if downgrade:
            script.module.downgrade()
        else:
            script.module.upgrade()


def run_revision(connection: Connection, revision: str) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "src" / "alembic.ini"))
    script = ScriptDirectory.from_config(config).get_revision(revision)
    assert script is not None
    with Operations.context(MigrationContext.configure(connection)):
        script.module.upgrade()


def downgrade_revision(connection: Connection, revision: str) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "src" / "alembic.ini"))
    script = ScriptDirectory.from_config(config).get_revision(revision)
    assert script is not None
    with Operations.context(MigrationContext.configure(connection)):
        script.module.downgrade()


async def test_daily_usage_migration_backfills_history_and_round_trips(
    migration_connection: AsyncConnection,
) -> None:
    connection = migration_connection
    await connection.run_sync(run_initial)
    for revision in ("0002", "0003", "0004", "0005", "0006"):
        await connection.run_sync(lambda sync: run_revision(sync, revision))
    user_id = await connection.scalar(
        text("INSERT INTO users (vk_user_id) VALUES (780) RETURNING id")
    )
    session_id = await connection.scalar(
        text("""
            INSERT INTO study_sessions (
                user_id, historical_deck_id, study_date, timezone, status,
                total_cards, completed_cards, daily_total_cards_limit,
                daily_new_cards_limit, scheduler_config, started_at,
                last_activity_at, day_end_at, expires_at
            ) VALUES (
                :user_id, 77, '2026-11-01', 'UTC', 'active',
                2, 0, 125, 12, '{}'::jsonb, now(), now(), now(), now()
            ) RETURNING id
        """),
        {"user_id": user_id},
    )
    await connection.execute(
        text("""
            INSERT INTO study_session_cards (
                session_id, card_id, snapshot, order_index, fsrs_state, was_new
            ) VALUES
                (:session_id, 91, jsonb_build_object('id', 91), 0, '{}', false),
                (:session_id, 92, jsonb_build_object('id', 92), 1, '{}', false)
        """),
        {"session_id": session_id},
    )
    await connection.execute(
        text("""
            INSERT INTO review_logs (
                user_id, card_id, deck_id, session_id, study_date,
                answer_token, rating, was_new, result, reviewed_at
            ) VALUES
                (:user_id, 91, 77, :session_id, '2026-11-01',
                    'old-1', 1, false, '{}', now()),
                (:user_id, 91, 77, :session_id, '2026-11-01',
                    'old-2', 3, true, '{}', now()),
                (:user_id, 91, 77, :session_id, '2026-11-01',
                    'old-3', 3, false, '{}', now()),
                (:user_id, 92, 77, :session_id, '2026-11-01',
                    'old-4', 3, false, '{}', now()),
                (:user_id, 91, 77, :session_id, '2026-11-02',
                    'old-5', 3, false, '{}', now())
        """),
        {"user_id": user_id, "session_id": session_id},
    )

    async def check_usage() -> None:
        rows = (
            await connection.execute(
                text("""
                    SELECT study_date::text, total_used, new_used
                    FROM study_daily_usage ORDER BY study_date
                """)
            )
        ).all()
        assert [tuple(row) for row in rows] == [
            ("2026-11-01", 2, 1),
            ("2026-11-02", 1, 0),
        ]
        assert (
            await connection.scalar(text("SELECT count(*) FROM study_daily_cards")) == 3
        )
        assert await connection.scalar(text("SELECT count(*) FROM review_logs")) == 5

    await connection.run_sync(lambda sync: run_revision(sync, "0007"))
    await check_usage()

    def check_indexes(sync: Connection) -> None:
        inspector = inspect(sync)
        assert set(inspector.get_table_names()) == set(Base.metadata.tables)
        for table in ("learning_cycles", "study_sessions"):
            assert any(
                index["column_names"] == ["membership_id"]
                for index in inspector.get_indexes(table)
            )

    await connection.run_sync(check_indexes)
    await connection.run_sync(lambda sync: downgrade_revision(sync, "0007"))
    assert await connection.scalar(text("SELECT count(*) FROM review_logs")) == 5
    await connection.run_sync(lambda sync: run_revision(sync, "0007"))
    await check_usage()


async def test_fsrs_migration_rejects_existing_history_without_data_loss(
    migration_connection: AsyncConnection,
) -> None:
    connection = migration_connection
    await connection.run_sync(run_initial)
    for revision in ("0002", "0003", "0004"):
        await connection.run_sync(lambda sync: run_revision(sync, revision))
    await connection.execute(text("INSERT INTO users (vk_user_id) VALUES (777)"))
    await connection.execute(
        text(
            "INSERT INTO study_sessions (user_id, timezone) "
            "SELECT id, 'UTC' FROM users WHERE vk_user_id = 777"
        )
    )
    with pytest.raises(DBAPIError, match="Legacy study history"):
        async with connection.begin_nested():
            await connection.run_sync(lambda sync: run_revision(sync, "0005"))
    assert await connection.scalar(text("SELECT count(*) FROM study_sessions")) == 1
    assert (
        await connection.scalar(
            text("SELECT daily_total_cards_limit FROM users WHERE vk_user_id = 777")
        )
        == 125
    )


async def test_fsrs_migrations_apply_with_default_limits(
    migration_connection: AsyncConnection,
) -> None:
    connection = migration_connection
    await connection.run_sync(run_initial)
    await connection.execute(
        text("INSERT INTO users (vk_user_id, daily_cards_limit) VALUES (778, 35)")
    )
    for revision in ("0002", "0003", "0004", "0005"):
        await connection.run_sync(lambda sync: run_revision(sync, revision))
    row = (
        await connection.execute(
            text(
                "SELECT daily_total_cards_limit, daily_new_cards_limit "
                "FROM users WHERE vk_user_id = 778"
            )
        )
    ).one()
    assert tuple(row) == (125, 12)
    tables = await connection.run_sync(
        lambda sync: set(inspect(sync).get_table_names())
    )
    assert tables == set(Base.metadata.tables) - {
        "study_daily_cards",
        "study_daily_usage",
    }


async def test_fsrs_parameters_migration_preserves_existing_users_and_sessions(
    migration_connection: AsyncConnection,
) -> None:
    connection = migration_connection
    await connection.run_sync(run_initial)
    for revision in ("0002", "0003", "0004", "0005"):
        await connection.run_sync(lambda sync: run_revision(sync, revision))
    user_id = await connection.scalar(
        text(
            "INSERT INTO users (vk_user_id, first_name, settings) "
            "VALUES (779, 'Иван', '{\"theme\": \"dark\"}'::jsonb) RETURNING id"
        )
    )
    await connection.execute(
        text("""
            INSERT INTO study_sessions (
                user_id, historical_deck_id, study_date, timezone, status,
                total_cards, completed_cards, daily_total_cards_limit,
                daily_new_cards_limit, scheduler_config, started_at,
                last_activity_at, day_end_at, expires_at
            ) VALUES (
                :user_id, 77, '2026-11-01', 'UTC', 'active',
                1, 0, 125, 12, '{}'::jsonb, now(), now(), now(), now()
            )
        """),
        {"user_id": user_id},
    )
    await connection.run_sync(lambda sync: run_revision(sync, "0006"))
    row = (
        await connection.execute(
            text(
                "SELECT first_name, settings, daily_total_cards_limit, fsrs_parameters "
                "FROM users WHERE id = :id"
            ),
            {"id": user_id},
        )
    ).one()
    assert row.first_name == "Иван"
    assert row.settings == {"theme": "dark"}
    assert row.daily_total_cards_limit == 125
    assert row.fsrs_parameters is None
    assert await connection.scalar(text("SELECT count(*) FROM study_sessions")) == 1


@pytest_asyncio.fixture
async def migration_connection(
    validated_migration_database_url,
) -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(validated_migration_database_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                schema = f"migration_{secrets.token_hex(8)}"
                await connection.execute(CreateSchema(schema))
                await connection.execute(text(f"SET LOCAL search_path TO {schema}"))
                yield connection
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def test_initial_schema_round_trip(migration_connection: AsyncConnection) -> None:
    connection = migration_connection
    await connection.run_sync(run_initial)

    def check_schema(sync: Connection) -> None:
        inspector = inspect(sync)

        assert set(inspector.get_table_names()) == set(Base.metadata.tables) - {
            "learning_cycles",
            "study_daily_cards",
            "study_daily_usage",
        }
        columns = {column["name"]: column for column in inspector.get_columns("users")}
        assert not ({"login", "password_hash", "token_version"} & columns.keys())
        assert columns["vk_user_id"]["nullable"] is False
        assert isinstance(columns["id"]["type"], BigInteger)
        assert columns["id"].get("identity") is not None

    await connection.run_sync(check_schema)
    await connection.run_sync(lambda sync: run_initial(sync, downgrade=True))
    assert await connection.run_sync(lambda sync: inspect(sync).get_table_names()) == []
    assert (
        await connection.scalar(
            text(
                "SELECT COUNT(*) FROM pg_type AS t "
                "JOIN pg_namespace AS n ON n.oid=t.typnamespace "
                "WHERE n.nspname=current_schema() AND t.typtype='e'"
            )
        )
        == 0
    )
    await connection.run_sync(run_initial)
    await connection.run_sync(check_schema)


async def test_initial_schema_requires_valid_unique_vk_ids(
    migration_connection: AsyncConnection,
) -> None:
    connection = migration_connection
    await connection.run_sync(run_initial)
    assert (
        await connection.scalar(
            text("INSERT INTO users (vk_user_id) VALUES (12345678) RETURNING id")
        )
        == 1
    )
    for statement in (
        "INSERT INTO users DEFAULT VALUES",
        "INSERT INTO users (vk_user_id) VALUES (0)",
        "INSERT INTO users (vk_user_id) VALUES (12345678)",
    ):
        with pytest.raises(IntegrityError):
            async with connection.begin_nested():
                await connection.execute(text(statement))


async def test_duplicate_activity_index_migration_round_trip(
    migration_connection: AsyncConnection,
) -> None:
    connection = migration_connection
    await connection.run_sync(run_initial)

    def indexes(sync: Connection) -> set[str]:
        return {
            index["name"] for index in inspect(sync).get_indexes("user_daily_activity")
        }

    assert "idx_user_activity_recent" in await connection.run_sync(indexes)
    await connection.run_sync(
        lambda sync: run_activity_index_migration(sync, downgrade=False)
    )
    assert "idx_user_activity_recent" not in await connection.run_sync(indexes)
    await connection.run_sync(
        lambda sync: run_activity_index_migration(sync, downgrade=True)
    )
    assert "idx_user_activity_recent" in await connection.run_sync(indexes)


async def test_nullable_deck_migration_preserves_data_and_rejects_lossy_downgrade(
    migration_connection: AsyncConnection,
) -> None:
    connection = migration_connection
    await connection.run_sync(run_initial)
    await connection.run_sync(
        lambda sync: run_activity_index_migration(sync, downgrade=False)
    )
    old = (
        await connection.execute(
            text(
                "INSERT INTO decks (title, subject, share_code) "
                "VALUES ('old', 'physics', 'OLDdeck1') "
                "RETURNING id, subject, cover_color"
            )
        )
    ).one()
    assert old.subject == "physics" and old.cover_color == "gradient-blue"

    await connection.run_sync(
        lambda sync: run_nullable_deck_migration(sync, downgrade=False)
    )

    def columns(sync: Connection) -> dict:
        return {column["name"]: column for column in inspect(sync).get_columns("decks")}

    upgraded = await connection.run_sync(columns)
    assert upgraded["subject"]["nullable"] is True
    assert upgraded["cover_color"]["nullable"] is True
    assert upgraded["cover_color"]["default"] is None
    persisted = (
        await connection.execute(
            text("SELECT subject, cover_color FROM decks WHERE id = :id"),
            {"id": old.id},
        )
    ).one()
    assert persisted.subject == "physics" and persisted.cover_color == "gradient-blue"
    new = (
        await connection.execute(
            text(
                "INSERT INTO decks (title, share_code) VALUES ('new', 'NEWdeck1') "
                "RETURNING id, subject, cover_color"
            )
        )
    ).one()
    assert new.subject is None and new.cover_color is None

    with pytest.raises(IntegrityError):
        async with connection.begin_nested():
            await connection.run_sync(
                lambda sync: run_nullable_deck_migration(sync, downgrade=True)
            )
    await connection.execute(
        text("UPDATE decks SET subject = 'physics' WHERE id = :id"), {"id": new.id}
    )
    with pytest.raises(IntegrityError):
        async with connection.begin_nested():
            await connection.run_sync(
                lambda sync: run_nullable_deck_migration(sync, downgrade=True)
            )
    still_nullable = await connection.run_sync(columns)
    assert still_nullable["subject"]["nullable"] is True
    assert still_nullable["cover_color"]["nullable"] is True

    await connection.execute(
        text("UPDATE decks SET cover_color = 'blue' WHERE id = :id"), {"id": new.id}
    )
    await connection.run_sync(
        lambda sync: run_nullable_deck_migration(sync, downgrade=True)
    )
    downgraded = await connection.run_sync(columns)
    assert downgraded["subject"]["nullable"] is False
    assert downgraded["cover_color"]["nullable"] is False
    assert "gradient-blue" in downgraded["cover_color"]["default"]
