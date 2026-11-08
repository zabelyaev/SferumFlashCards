from fastapi import APIRouter, Depends

from api.dependencies.auth import get_current_user, require_app_key
from common.config import settings

from .flashcards import router as flashcards_router
from .study.routes import router as study_router
from .users import router as user_router

router = APIRouter(
    prefix=settings.api.v1.prefix, tags=["V1"], dependencies=[Depends(require_app_key)]
)

router.include_router(user_router)
router.include_router(flashcards_router, dependencies=[Depends(get_current_user)])
router.include_router(study_router, dependencies=[Depends(get_current_user)])
