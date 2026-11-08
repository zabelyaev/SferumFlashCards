from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.accounts.database.sqla_uow import SQLAUnitOfWork
from application.accounts.users.database.repository import SQLAUserRepository
from application.activity.database.repository import SQLAActivityRepository


async def test_accounts_flush_uses_shared_session_and_stays_rollbackable() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.in_transaction.return_value = True
    uow = SQLAUnitOfWork(MagicMock(return_value=session))
    with pytest.raises(RuntimeError, match="abort"):
        async with uow:
            assert isinstance(uow.users, SQLAUserRepository)
            assert isinstance(uow.activity, SQLAActivityRepository)
            assert uow.users._session is session
            assert uow.activity._session is session
            await uow.flush()
            session.flush.assert_awaited_once()
            session.commit.assert_not_awaited()
            raise RuntimeError("abort")
    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()


async def test_accounts_flush_requires_entered_uow() -> None:
    uow = SQLAUnitOfWork(MagicMock())
    with pytest.raises(RuntimeError, match="has not been entered"):
        await uow.flush()
