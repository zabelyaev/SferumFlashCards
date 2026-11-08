from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware

import application.models  # noqa: F401
from api import router as api_router
from api.headers import HEADERS
from common.config import settings
from common.database import DatabaseHelper
from common.exceptions.handlers import mount_exceptions_handlers
from common.middleware.json_body_limit import (
    MAX_JSON_BODY_CHARACTERS,
    JsonBodyLimitMiddleware,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_helper = DatabaseHelper(settings.db)
    app.state.database_helper = database_helper
    try:
        yield
    finally:
        await database_helper.dispose()


def create_app() -> FastAPI:
    if settings.auth.app_key is None:
        raise RuntimeError("APP_CONFIG__AUTH__APP_KEY must be configured.")

    app = FastAPI(
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        swagger_ui_oauth2_redirect_url=None,
        responses={
            413: {
                "description": (
                    "JSON request body exceeds "
                    f"{MAX_JSON_BODY_CHARACTERS} UTF-8 characters."
                ),
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"detail": {"type": "string"}},
                            "required": ["detail"],
                        }
                    }
                },
            }
        },
        middleware=[
            Middleware(JsonBodyLimitMiddleware, cors_origins=settings.cors.origins),
            Middleware(
                CORSMiddleware,
                allow_origins=settings.cors.origins,
                allow_credentials=False,
                allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                allow_headers=HEADERS,
            ),
        ],
    )

    app.include_router(api_router)
    mount_exceptions_handlers(app)

    return app


main_app = create_app()


def run() -> None:
    uvicorn.run(
        "main:main_app",
        host=settings.run.host,
        port=settings.run.port,
        workers=settings.run.workers,
        backlog=settings.run.backlog,
        timeout_keep_alive=settings.run.timeout_keep_alive,
        timeout_graceful_shutdown=settings.run.timeout_graceful_shutdown,
    )


if __name__ == "__main__":
    run()
