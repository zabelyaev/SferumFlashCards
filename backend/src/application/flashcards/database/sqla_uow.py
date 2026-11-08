from typing import TYPE_CHECKING

from application.flashcards.cards.database.repository import SQLACardRepository
from application.flashcards.decks.database.repository import SQLADeckRepository
from application.flashcards.library.database.repository import SQLALibraryRepository

if TYPE_CHECKING:
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from application.flashcards.database.uow import (
        CardRepository,
        DeckRepository,
        FlashcardsUnitOfWork,
        LibraryRepository,
    )


class SQLAFlashcardsUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.decks: DeckRepository
        self.cards: CardRepository
        self.library: LibraryRepository

    async def __aenter__(self) -> SQLAFlashcardsUnitOfWork:
        self._session = self._session_factory()
        self.decks = SQLADeckRepository(self._session)
        self.cards = SQLACardRepository(self._session)
        self.library = SQLALibraryRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if session.in_transaction():
                await session.rollback()
        finally:
            await session.close()
            self._session = None

    async def flush(self) -> None:
        await self._require_session().flush()

    async def commit(self) -> None:
        await self._require_session().commit()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Unit of Work has not been entered.")
        return self._session


class SQLAFlashcardsUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> FlashcardsUnitOfWork:
        return SQLAFlashcardsUnitOfWork(self._session_factory)
