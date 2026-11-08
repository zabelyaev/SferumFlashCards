from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from application.accounts.users.contracts.inputs import UserSettingsReplaceInput
from application.accounts.users.database.models import User
from application.accounts.users.database.repository import SQLAUserRepository
from common.exceptions.forbidden import ForbiddenError


async def test_user_repository_uses_no_key_update_lock() -> None:
    session = AsyncMock()
    user = User(id=7, vk_user_id=123)
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = user
    result = await SQLAUserRepository(session).get_by_id(7, no_key_update=True)
    assert result is user
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR NO KEY UPDATE OF users" in sql


@pytest.mark.parametrize("is_active", [False, True])
async def test_auth_selects_only_id_and_active_without_lock(is_active: bool) -> None:
    session = AsyncMock()
    session.execute.return_value = MagicMock()
    session.execute.return_value.one_or_none.return_value = SimpleNamespace(
        id=7, is_active=is_active
    )
    result = await SQLAUserRepository(session).find_current_by_vk_id(123)
    assert result is not None
    assert result.model_dump() == {"id": 7, "is_active": is_active}
    statement = session.execute.await_args.args[0]
    assert list(statement.selected_columns.keys()) == ["id", "is_active"]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "WHERE users.vk_user_id =" in str(compiled)
    assert "FOR UPDATE" not in str(compiled)
    assert "FOR NO KEY UPDATE" not in str(compiled)
    assert list(compiled.params.values()) == [123]
    session.execute.assert_awaited_once()
    session.flush.assert_not_awaited()


async def test_auth_projection_returns_none_for_unknown_user() -> None:
    session = AsyncMock()
    session.execute.return_value = MagicMock()
    session.execute.return_value.one_or_none.return_value = None
    assert await SQLAUserRepository(session).find_current_by_vk_id(123) is None
    session.execute.assert_awaited_once()


@pytest.mark.parametrize("is_active", [False, True])
async def test_empty_sync_locks_existing_user_without_upsert(is_active: bool) -> None:
    session = AsyncMock()
    user = User(id=7, vk_user_id=123, is_active=is_active)
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = user
    repo = SQLAUserRepository(session)
    if is_active:
        assert await repo.upsert_by_vk_id(123, profile={}) is user
    else:
        with pytest.raises(ForbiddenError):
            await repo.upsert_by_vk_id(123, profile={})
    session.execute.assert_awaited_once()
    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert sql.startswith("SELECT ")
    assert "FOR NO KEY UPDATE OF users" in sql
    assert "INSERT" not in sql
    session.flush.assert_not_awaited()


@pytest.mark.parametrize("disabled_race", [False, True])
async def test_first_empty_sync_retains_atomic_guarded_upsert(
    disabled_race: bool,
) -> None:
    session = AsyncMock()
    missing, inserted = MagicMock(), MagicMock()
    missing.scalar_one_or_none.return_value = None
    user = User(id=7, vk_user_id=123, is_active=True)
    inserted.scalar_one_or_none.return_value = None if disabled_race else user
    session.execute.side_effect = [missing, inserted]
    repo = SQLAUserRepository(session)
    if disabled_race:
        with pytest.raises(ForbiddenError):
            await repo.upsert_by_vk_id(123, profile={})
    else:
        assert await repo.upsert_by_vk_id(123, profile={}) is user
    assert session.execute.await_count == 2
    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (vk_user_id) DO UPDATE" in sql
    assert "WHERE users.is_active IS true" in sql
    assert "RETURNING users." in sql


async def test_explicit_sync_fields_keep_single_guarded_upsert() -> None:
    session = AsyncMock()
    user = User(id=7, vk_user_id=123, is_active=True)
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = user
    assert (
        await SQLAUserRepository(session).upsert_by_vk_id(
            123, profile={"first_name": "A"}
        )
        is user
    )
    session.execute.assert_awaited_once()
    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (vk_user_id) DO UPDATE" in sql
    assert "updated_at = now()" in sql
    assert "WHERE users.is_active IS true" in sql


@pytest.mark.parametrize("operation", ["profile", "settings"])
@pytest.mark.parametrize("is_active", [False, True])
async def test_mutations_defer_flush_of_locked_user(
    operation: str, is_active: bool
) -> None:
    session = AsyncMock()
    user = User(
        id=7, vk_user_id=123, is_active=is_active, first_name="Before", settings={}
    )
    repo = SQLAUserRepository(session)

    async def mutate():
        if operation == "profile":
            await repo.update(user, profile={"first_name": "After"})
        else:
            await repo.replace_settings(
                user, data=UserSettingsReplaceInput(settings={"theme": "dark"})
            )

    if is_active:
        await mutate()
        assert user.first_name == ("After" if operation == "profile" else "Before")
        assert user.settings == ({"theme": "dark"} if operation == "settings" else {})
    else:
        with pytest.raises(ForbiddenError):
            await mutate()
        assert user.first_name == "Before"
        assert user.settings == {}
    session.execute.assert_not_awaited()
    session.flush.assert_not_awaited()


async def test_delete_retains_stronger_user_lock() -> None:
    session = AsyncMock()
    user = User(id=7, vk_user_id=123)
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = user
    await SQLAUserRepository(session).delete(7)
    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE OF users" in sql
    session.delete.assert_awaited_once_with(user)
