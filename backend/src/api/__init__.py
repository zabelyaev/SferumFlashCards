from fastapi import APIRouter

from common.config import settings

from .documentation import router as documentation_router
from .v1 import router as v1_router

router = APIRouter()

router.include_router(v1_router, prefix=settings.api.prefix)
router.include_router(documentation_router)
