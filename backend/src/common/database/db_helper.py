from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from common.config.database import DatabaseConfig


class DatabaseHelper:
    def __init__(
        self,
        config: DatabaseConfig,
    ) -> None:
        self.engine: AsyncEngine = create_async_engine(
            config.async_url,
            echo=config.sqla.echo,
            echo_pool=config.sqla.echo_pool,
            pool_size=config.sqla.pool_size,
            max_overflow=config.sqla.max_overflow,
            pool_pre_ping=True,
        )
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    async def dispose(self) -> None:
        await self.engine.dispose()
