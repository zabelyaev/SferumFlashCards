from fastapi import APIRouter

from common.config import settings

from .profile import router as profile_router
from .settings_routes import router as settings_router
from .sync import router as sync_router

router = APIRouter(prefix=settings.api.v1.users, tags=["Users"])

router.include_router(sync_router)
router.include_router(profile_router)
router.include_router(settings_router)
