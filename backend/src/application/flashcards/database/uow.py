from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType
    from typing import Self

    from application.flashcards.cards.contracts.inputs import (
        CardCreateInput,
        CardListInput,
        CardUpdateInput,
    )
    from application.flashcards.cards.database.models import Card
    from application.flashcards.decks.contracts.inputs import (
        DeckCatalogInput,
        DeckCreateInput,
        DeckUpdateInput,
    )
    from application.flashcards.decks.database.models import Deck
    from application.flashcards.library.contracts.inputs import LibraryListInput
    from application.flashcards.library.database.models import UserDeck


class DeckRepository(Protocol):
    async def get_by_id(
        self, deck_id: int, *, for_update: bool = False, for_share: bool = False
    ) -> Deck: ...

    async def get_by_share_code(
        self, share_code: str, *, for_update: bool = False, for_share: bool = False
    ) -> Deck: ...

    async def list_catalog(
        self, data: DeckCatalogInput
    ) -> tuple[Sequence[Deck], int]: ...

    async def create(self, *, author_id: int, data: DeckCreateInput) -> Deck: ...

    async def delete(self, deck: Deck) -> None: ...

    async def update(self, deck: Deck, data: DeckUpdateInput) -> None: ...


class CardRepository(Protocol):
    async def list_for_deck(self, deck_id: int) -> Sequence[Card]: ...

    async def list_page_for_deck(
        self, deck_id: int, data: CardListInput, *, total: int
    ) -> tuple[Sequence[Card], int]: ...

    async def get_by_id(self, card_id: int, *, deck_id: int) -> Card: ...

    async def append(self, *, deck_id: int, data: CardCreateInput) -> Card: ...

    async def delete(self, card: Card) -> None: ...

    async def update(self, card: Card, data: CardUpdateInput) -> None: ...


class LibraryRepository(Protocol):
    async def find_membership(self, user_id: int, deck_id: int) -> UserDeck | None: ...

    async def ensure_membership(self, *, user_id: int, deck_id: int) -> UserDeck: ...

    async def remove_membership(self, *, user_id: int, deck_id: int) -> None: ...

    async def list_decks_for_user(
        self, user_id: int, data: LibraryListInput
    ) -> tuple[Sequence[Deck], int]: ...


class FlashcardsUnitOfWork(Protocol):
    @property
    def decks(self) -> DeckRepository: ...

    @property
    def cards(self) -> CardRepository: ...

    @property
    def library(self) -> LibraryRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...


class FlashcardsUnitOfWorkFactory(Protocol):
    def __call__(self) -> FlashcardsUnitOfWork: ...
