from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.database import DatabaseHelper


def get_database_helper(request: Request) -> DatabaseHelper:
    return cast(DatabaseHelper, request.app.state.database_helper)


def get_session_factory(
    database_helper: DatabaseHelperDep,
) -> async_sessionmaker[AsyncSession]:
    return database_helper.session_factory


type DatabaseHelperDep = Annotated[
    DatabaseHelper,
    Depends(get_database_helper),
]
type SessionFactoryDep = Annotated[
    async_sessionmaker[AsyncSession],
    Depends(get_session_factory),
]
