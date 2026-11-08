import json
import os
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

import main
from api.v1 import router as v1_router
from common.config import settings
from common.config.documentation import DocumentationConfig

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

PREFIX = "/private/reference"
DOC_PATHS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")
DOC_AUTH = ("reader", "docs-password:with-colon")
SRC_DIR = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture
def app_factory(monkeypatch):
    def build(config: DocumentationConfig) -> FastAPI:

        spec = spec_from_file_location(
            "api._documentation_under_test", SRC_DIR / "api" / "documentation.py"
        )
        assert spec is not None and spec.loader is not None
        documentation = module_from_spec(spec)
        with monkeypatch.context() as context:
            context.setattr(settings, "documentation", config)
            spec.loader.exec_module(documentation)

        router = APIRouter()
        router.include_router(v1_router, prefix=settings.api.prefix)
        router.include_router(documentation.router)
        with monkeypatch.context() as context:
            context.setattr(main, "api_router", router)
            return main.create_app()

    return build


@pytest.fixture
def docs_app(app_factory) -> FastAPI:
    return app_factory(
        DocumentationConfig(
            prefix=PREFIX,
            enabled=True,
            login=DOC_AUTH[0],
            password=SecretStr(DOC_AUTH[1]),
        )
    )


@pytest_asyncio.fixture
async def client(docs_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=docs_app), base_url="http://test"
    ) as client:
        yield client


@pytest.mark.parametrize("path", DOC_PATHS)
@pytest.mark.parametrize("enabled", [False, True])
async def test_original_documentation_urls_are_never_registered(
    app_factory, path, enabled
) -> None:
    config = DocumentationConfig(
        prefix=PREFIX,
        enabled=enabled,
        login=DOC_AUTH[0],
        password=SecretStr(DOC_AUTH[1]),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app_factory(config)), base_url="http://test"
    ) as client:
        response = await client.get(path, auth=DOC_AUTH)
    assert response.status_code == 404


@pytest.mark.parametrize("path", DOC_PATHS)
async def test_disabled_documentation_has_no_prefixed_routes_even_with_credentials(
    app_factory,
    path,
) -> None:
    app = app_factory(DocumentationConfig(prefix=PREFIX))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(PREFIX + path, auth=DOC_AUTH)
    assert response.status_code == 404
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None
    assert app.swagger_ui_oauth2_redirect_url is None


@pytest.mark.parametrize("path", DOC_PATHS)
async def test_every_documentation_route_prompts_for_basic_auth(client, path) -> None:
    response = await client.get(PREFIX + path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Basic realm="Documentation"'
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", DOC_PATHS)
@pytest.mark.parametrize(
    "auth", [("wrong", DOC_AUTH[1]), (DOC_AUTH[0], "wrong"), ("wrong", "wrong")]
)
async def test_every_documentation_route_rejects_wrong_credentials(
    client, path, auth
) -> None:
    response = await client.get(PREFIX + path, auth=auth)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Basic realm="Documentation"'
    assert DOC_AUTH[1] not in response.text


@pytest.mark.parametrize("path", DOC_PATHS)
@pytest.mark.parametrize(
    "authorization",
    ["Bearer not-a-token", "Basic !!!", "Basic dXNlcg==", "Basic /w=="],
)
async def test_malformed_authorization_cannot_bypass_documentation_auth(
    client, path, authorization
) -> None:
    response = await client.get(PREFIX + path, headers={"Authorization": authorization})
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")


@pytest.mark.parametrize("path", DOC_PATHS)
async def test_documentation_keys_are_independent_from_application_keys(
    client, path, app_headers
) -> None:

    response = await client.get(PREFIX + path, headers=app_headers)
    assert response.status_code == 401

    response = await client.get(PREFIX + path, auth=DOC_AUTH)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


async def test_swagger_and_redoc_use_protected_schema_and_redirect_urls(client) -> None:
    swagger = await client.get(PREFIX + "/docs", auth=DOC_AUTH)
    assert f"url: '{PREFIX}/openapi.json'" in swagger.text
    assert f"{PREFIX}/docs/oauth2-redirect" in swagger.text
    redoc = await client.get(PREFIX + "/redoc", auth=DOC_AUTH)
    assert f'spec-url="{PREFIX}/openapi.json"' in redoc.text


async def test_http_schema_matches_internal_schema_without_exposing_docs_auth(
    client, docs_app
) -> None:

    docs_app.openapi()
    response = await client.get(PREFIX + "/openapi.json", auth=DOC_AUTH)
    schema = response.json()
    assert schema == docs_app.openapi()
    assert schema["paths"]
    assert all(not path.startswith(PREFIX) for path in schema["paths"])
    assert set(schema["components"]["securitySchemes"]) == {"AppKey"}
    for path in schema["paths"].values():
        for operation in path.values():
            assert operation["security"] == [{"AppKey": []}]
    assert DOC_AUTH[0] not in response.text
    assert DOC_AUTH[1] not in response.text
    assert docs_app.openapi.__func__ is FastAPI.openapi


async def test_basic_credentials_do_not_authorize_business_requests(client) -> None:
    response = await client.post(
        "/api/v1/users/sync", auth=DOC_AUTH, json={"vk_user_id": 12345678}
    )
    assert response.status_code == 401


@pytest.mark.parametrize("root_path", ["/gateway", "/gateway/nested"])
async def test_documentation_urls_include_proxy_root_path(docs_app, root_path) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=docs_app, root_path=root_path),
        base_url="http://test",
    ) as client:
        swagger = await client.get(PREFIX + "/docs", auth=DOC_AUTH)
        redoc = await client.get(PREFIX + "/redoc", auth=DOC_AUTH)
        schema = await client.get(root_path + PREFIX + "/openapi.json", auth=DOC_AUTH)
    assert swagger.status_code == 200
    assert f"url: '{root_path}{PREFIX}/openapi.json'" in swagger.text
    assert f"{root_path}{PREFIX}/docs/oauth2-redirect" in swagger.text
    assert redoc.status_code == 200
    assert f'spec-url="{root_path}{PREFIX}/openapi.json"' in redoc.text
    assert schema.status_code == 200


@pytest.mark.parametrize("enabled", [False, True])
def test_startup_registers_documentation_through_root_api_router(enabled) -> None:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.startswith("APP_CONFIG__DOCUMENTATION"):
            del environment[key]
    environment.update(
        {
            "PYTHONPATH": str(SRC_DIR),
            "APP_CONFIG__DOCUMENTATION__PREFIX": PREFIX,
            "APP_CONFIG__DOCUMENTATION__ENABLED": str(enabled).lower(),
            "APP_CONFIG__DOCUMENTATION__LOGIN": DOC_AUTH[0],
            "APP_CONFIG__DOCUMENTATION__PASSWORD": DOC_AUTH[1],
        }
    )
    script = """
import asyncio
import json
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from common.config import settings
from main import main_app

async def check():
    config = settings.documentation
    auth = (config.login, config.password.get_secret_value())
    expected = 200 if config.enabled else 404
    async with AsyncClient(
        transport=ASGITransport(app=main_app), base_url="http://test"
    ) as client:
        for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
            assert (await client.get(path, auth=auth)).status_code == 404
            nested = await client.get("/api" + config.prefix + path, auth=auth)
            assert nested.status_code == 404
            response = await client.get(config.prefix + path, auth=auth)
            assert response.status_code == expected
            if config.enabled:
                assert (await client.get(config.prefix + path)).status_code == 401
        response = await client.post(
            "/api/v1/users/sync", json={"vk_user_id": 12345678}
        )
        assert response.status_code == 401
    assert main_app.openapi.__func__ is FastAPI.openapi
    paths = main_app.openapi()["paths"]
    assert "/api/v1/users/sync" in paths
    assert "/api/v1/users/me/profile" in paths
    assert not any(path.startswith(config.prefix) for path in paths)
    print(json.dumps({"enabled": config.enabled, "checked": True}))

asyncio.run(check())
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == {"enabled": enabled, "checked": True}


async def test_disabled_app_does_not_reuse_another_apps_schema_or_routes(
    app_factory,
    docs_app,
) -> None:
    docs_app.openapi()
    disabled = app_factory(DocumentationConfig())
    async with AsyncClient(
        transport=ASGITransport(app=disabled), base_url="http://test"
    ) as client:
        for prefix in (PREFIX, "/internal"):
            response = await client.get(prefix + "/openapi.json", auth=DOC_AUTH)
            assert response.status_code == 404
    assert disabled.openapi_schema is None
    assert disabled.openapi()["paths"] == docs_app.openapi()["paths"]
    assert disabled.openapi.__func__ is FastAPI.openapi


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
async def test_documentation_credentials_are_not_embedded_in_generated_html(
    client, path
) -> None:
    response = await client.get(PREFIX + path, auth=DOC_AUTH)
    assert response.status_code == 200
    assert DOC_AUTH[0] not in response.text
    assert DOC_AUTH[1] not in response.text
