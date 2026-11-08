import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from common.config import settings

DOCUMENTATION_REALM = "Documentation"
NO_STORE = {"Cache-Control": "no-store"}

config = settings.documentation
basic = HTTPBasic(auto_error=False, realm=DOCUMENTATION_REALM)


def require_credentials(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(basic)],
) -> None:
    if credentials is None:
        matches = (False,)
    else:
        matches = (
            secrets.compare_digest(
                credentials.username.encode(), config.login.encode()
            ),
            secrets.compare_digest(
                credentials.password.encode(),
                config.password.get_secret_value().encode(),
            ),
        )
    if not all(matches):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid documentation credentials.",
            headers={
                "WWW-Authenticate": f'Basic realm="{DOCUMENTATION_REALM}"',
                **NO_STORE,
            },
        )


router = APIRouter(
    prefix=config.prefix,
    dependencies=[Depends(require_credentials)],
    include_in_schema=False,
)


if config.enabled:

    def public_prefix(request: Request) -> str:
        return request.scope.get("root_path", "").rstrip("/") + config.prefix

    @router.get("/openapi.json", name="documentation_openapi")
    async def openapi_schema(request: Request) -> JSONResponse:
        return JSONResponse(request.app.openapi(), headers=NO_STORE)

    @router.get("/docs", name="documentation_swagger")
    async def swagger(request: Request) -> HTMLResponse:
        prefix = public_prefix(request)
        response = get_swagger_ui_html(
            openapi_url=f"{prefix}/openapi.json",
            title=f"{request.app.title} - Swagger UI",
            oauth2_redirect_url=f"{prefix}/docs/oauth2-redirect",
        )
        response.headers.update(NO_STORE)
        return response

    @router.get("/redoc", name="documentation_redoc")
    async def redoc(request: Request) -> HTMLResponse:
        response = get_redoc_html(
            openapi_url=f"{public_prefix(request)}/openapi.json",
            title=f"{request.app.title} - ReDoc",
        )
        response.headers.update(NO_STORE)
        return response

    @router.get("/docs/oauth2-redirect", name="documentation_oauth2_redirect")
    async def swagger_redirect() -> HTMLResponse:
        response = get_swagger_ui_oauth2_redirect_html()
        response.headers.update(NO_STORE)
        return response
