from fastapi import APIRouter

from .cards.routes import router as cards_router
from .decks.routes import router as decks_router
from .library.routes import router as library_router

router = APIRouter(tags=["Flashcards"])

router.include_router(decks_router)
router.include_router(
    cards_router,
)
router.include_router(
    library_router,
)
