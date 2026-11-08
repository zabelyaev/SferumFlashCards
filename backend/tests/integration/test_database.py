from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text

from common.database import DatabaseHelper

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def session_factory(
    validated_test_database,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    helper = DatabaseHelper(validated_test_database)
    try:
        yield helper.session_factory
    finally:
        await helper.dispose()


@pytest.mark.asyncio
async def test_runtime_database_role_has_no_schema_create_permission(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        can_create = await session.scalar(
            text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
        )

    assert can_create is False
