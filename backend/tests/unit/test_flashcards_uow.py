from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.flashcards.database.sqla_uow import SQLAFlashcardsUnitOfWork


async def test_uow_closes_shared_session_after_rollback_on_error() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.in_transaction.return_value = True
    factory = MagicMock(return_value=session)
    uow = SQLAFlashcardsUnitOfWork(factory)

    with pytest.raises(ValueError, match="abort"):
        async with uow:
            assert uow.decks._session is session
            assert uow.cards._session is session
            assert uow.library._session is session
            raise ValueError("abort")

    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()
    with pytest.raises(RuntimeError, match="has not been entered"):
        await uow.commit()


async def test_uow_closes_session_even_if_rollback_fails() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.in_transaction.return_value = True
    session.rollback.side_effect = RuntimeError("rollback failed")
    uow = SQLAFlashcardsUnitOfWork(MagicMock(return_value=session))

    with pytest.raises(RuntimeError, match="rollback failed"):
        async with uow:
            pass

    session.close.assert_awaited_once()
    with pytest.raises(RuntimeError, match="has not been entered"):
        await uow.flush()
