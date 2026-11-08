import asyncio
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.dependencies.services import get_user_service
from application.accounts.users.service import UserService
from common.middleware.json_body_limit import (
    MAX_JSON_BODY_CHARACTERS,
    JsonBodyLimitMiddleware,
)
from main import create_app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.types import Scope


def json_body(characters: int, letter: str = "a") -> bytes:
    prefix, suffix = '{"x":"', '"}'
    return (
        prefix + letter * (characters - len(prefix) - len(suffix)) + suffix
    ).encode()


@pytest_asyncio.fixture
async def limited_client(profile, user_headers) -> AsyncIterator:
    app = create_app()
    users = AsyncMock(spec=UserService)
    users.get_current.return_value = profile
    users.get_profile.return_value = profile

    async def replace_settings(user_id, model):
        return profile.model_copy(update={"settings": model.settings})

    users.replace_settings.side_effect = replace_settings
    app.dependency_overrides[get_user_service] = lambda: users
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=user_headers
    ) as client:
        yield client, users


@pytest.mark.parametrize("letter", ["a", "я", "😀"])
async def test_exact_character_limit_accepts_unicode(limited_client, letter) -> None:
    client, users = limited_client
    body = json_body(MAX_JSON_BODY_CHARACTERS, letter)
    assert len(body.decode()) == MAX_JSON_BODY_CHARACTERS
    response = await client.put(
        "/api/v1/users/me/settings",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["settings"] == json.loads(body)
    users.replace_settings.assert_awaited_once()


@pytest.mark.parametrize("letter", ["a", "я", "😀"])
@pytest.mark.parametrize(
    "media_type",
    [
        None,
        "application/json",
        "Application/JSON; charset=utf-8",
        "application/test+json",
    ],
)
async def test_one_extra_character_is_rejected_before_services(
    limited_client, letter, media_type
) -> None:
    client, users = limited_client
    headers = {"Content-Type": media_type} if media_type else {}
    response = await client.put(
        "/api/v1/users/me/settings",
        content=json_body(MAX_JSON_BODY_CHARACTERS + 1, letter),
        headers=headers,
    )
    assert response.status_code == 413
    assert "65536" in response.json()["detail"]
    assert response.headers["connection"] == "close"
    users.get_current.assert_not_awaited()
    users.replace_settings.assert_not_awaited()


async def test_whitespace_and_escape_sequences_count_in_raw_json(
    limited_client,
) -> None:
    client, users = limited_client

    compact = b'{"x":"' + b"\\u044f" * 100 + b'"}'
    body = compact + b" " * (MAX_JSON_BODY_CHARACTERS - len(compact))
    accepted = await client.put(
        "/api/v1/users/me/settings",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["settings"] == {"x": "я" * 100}
    users.get_current.reset_mock()
    users.replace_settings.reset_mock()
    rejected = await client.put(
        "/api/v1/users/me/settings",
        content=body + b" ",
        headers={"Content-Type": "application/json"},
    )
    assert rejected.status_code == 413
    users.get_current.assert_not_awaited()
    users.replace_settings.assert_not_awaited()


@pytest.mark.parametrize("extra", [0, 1])
async def test_chunked_body_with_split_utf8_characters(limited_client, extra) -> None:
    client, users = limited_client
    body = json_body(MAX_JSON_BODY_CHARACTERS + extra, "😀")

    async def chunks():

        for start, end in ((0, 7), (7, 8), (8, 9), (9, len(body))):
            yield body[start:end]

    request = client.build_request(
        "PUT",
        "/api/v1/users/me/settings",
        content=chunks(),
        headers={"Content-Type": "application/json"},
    )
    assert "content-length" not in request.headers
    response = await client.send(request)
    assert response.status_code == (413 if extra else 200)
    if extra:
        users.replace_settings.assert_not_awaited()
    else:
        assert response.json()["settings"] == json.loads(body)


@pytest.mark.parametrize("payload", [b'"\xff"', b'{"x":"\xf0\x9f'])
async def test_invalid_or_incomplete_utf8_is_controlled(
    limited_client, payload
) -> None:
    client, users = limited_client
    response = await client.put(
        "/api/v1/users/me/settings",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    users.get_current.assert_not_awaited()
    users.replace_settings.assert_not_awaited()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/users/sync"),
        ("GET", "/api/v1/users/me/profile"),
        ("PATCH", "/api/v1/users/me/profile"),
        ("PUT", "/api/v1/users/me/settings"),
        ("POST", "/api/v1/decks"),
        ("GET", "/api/v1/decks"),
        ("GET", "/api/v1/decks/share/Abcd1234"),
        ("GET", "/api/v1/decks/1"),
        ("PATCH", "/api/v1/decks/1"),
        ("DELETE", "/api/v1/decks/1"),
        ("GET", "/api/v1/decks/1/cards"),
        ("POST", "/api/v1/decks/1/cards"),
        ("PATCH", "/api/v1/decks/1/cards/1"),
        ("DELETE", "/api/v1/decks/1/cards/1"),
        ("GET", "/api/v1/library/decks"),
        ("PUT", "/api/v1/library/decks/share/Abcd1234"),
        ("PUT", "/api/v1/library/decks/1"),
        ("DELETE", "/api/v1/library/decks/1"),
        ("POST", "/api/v1/study/sessions"),
        ("GET", "/api/v1/study/sessions/active"),
        ("GET", "/api/v1/study/sessions/1"),
        ("POST", "/api/v1/study/sessions/1/reviews"),
    ],
)
async def test_limit_applies_to_all_operations_before_auth_or_json_parsing(
    method, path
) -> None:
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.request(
            method,
            path,
            content=b" " * (MAX_JSON_BODY_CHARACTERS + 1),
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 413


async def test_size_error_keeps_cors_headers(limited_client) -> None:
    client, _ = limited_client
    response = await client.put(
        "/api/v1/users/me/settings",
        content=b" " * (MAX_JSON_BODY_CHARACTERS + 1),
        headers={"Content-Type": "application/json", "Origin": "https://test.invalid"},
    )
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "*"


@pytest.mark.parametrize("oversized", [False, True])
async def test_json_preflight_is_limited_before_cors(oversized) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.request(
            "OPTIONS",
            "/api/v1/decks",
            content=b" " * (MAX_JSON_BODY_CHARACTERS + 1) if oversized else b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://test.invalid",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert response.status_code == (413 if oversized else 200)
    assert response.headers["access-control-allow-origin"] == "*"


@pytest.mark.parametrize("allowed", [False, True])
async def test_rejection_uses_configured_origin_policy(monkeypatch, allowed) -> None:
    from common.config import settings

    monkeypatch.setattr(settings.cors, "origins", ["https://allowed.invalid"])
    origin = "https://allowed.invalid" if allowed else "https://blocked.invalid"
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.request(
            "OPTIONS",
            "/api/v1/decks",
            content=b" " * (MAX_JSON_BODY_CHARACTERS + 1),
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
            },
        )
    assert response.status_code == 413
    if allowed:
        assert response.headers["access-control-allow-origin"] == origin
        assert "Origin" in response.headers["vary"]
    else:
        assert "access-control-allow-origin" not in response.headers


def http_scope(headers=(), version="1.1") -> Scope:
    return {"type": "http", "http_version": version, "headers": list(headers)}


async def test_oversized_length_sends_error_before_discarding_upload() -> None:
    app, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
    receive.return_value = {
        "type": "http.request",
        "body": b"x" * 41,
        "more_body": False,
    }

    async def received():
        assert send.await_args_list[0].args[0]["status"] == 413
        assert send.await_args_list[1].args[0]["more_body"] is True
        return receive.return_value

    receive.side_effect = received
    limiter = JsonBodyLimitMiddleware(app, max_characters=10)
    await limiter(http_scope([(b"content-length", b"41")]), receive, send)
    assert send.await_args_list[0].args[0]["status"] == 413
    receive.assert_awaited_once()
    assert send.await_args_list[-1].args[0] == {
        "type": "http.response.body",
        "body": b"",
    }
    app.assert_not_awaited()


@pytest.mark.parametrize("content_length", [None, b"1", b"invalid"])
async def test_streaming_count_does_not_trust_length_and_bounds_discard(
    content_length,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "common.middleware.json_body_limit.REJECT_DRAIN_BUDGET_BYTES", 4
    )
    app, send = AsyncMock(), AsyncMock()
    receive = AsyncMock(
        side_effect=[
            {"type": "http.request", "body": b"a" * 10, "more_body": True},
            {"type": "http.request", "body": b"b", "more_body": True},
            {"type": "http.request", "body": b"x" * 4, "more_body": True},
            AssertionError("must not discard beyond the rejection budget"),
        ]
    )
    headers = [] if content_length is None else [(b"content-length", content_length)]
    await JsonBodyLimitMiddleware(app, max_characters=10)(
        http_scope(headers), receive, send
    )
    assert send.await_args_list[0].args[0]["status"] == 413
    assert receive.await_count == 3
    app.assert_not_awaited()


async def test_byte_bound_also_works_without_content_length() -> None:
    app, send = AsyncMock(), AsyncMock()
    receive = AsyncMock(
        side_effect=[
            {
                "type": "http.request",
                "body": b"\xff" * 41,
                "more_body": True,
            },
            {"type": "http.disconnect"},
        ]
    )
    await JsonBodyLimitMiddleware(app, max_characters=10)(http_scope(), receive, send)
    assert send.await_args_list[0].args[0]["status"] == 413
    app.assert_not_awaited()


async def test_rejection_discard_stops_when_whole_event_crosses_budget(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "common.middleware.json_body_limit.REJECT_DRAIN_BUDGET_BYTES", 4
    )
    app, send = AsyncMock(), AsyncMock()
    receive = AsyncMock(
        side_effect=[
            {"type": "http.request", "body": b"abc", "more_body": True},
            {"type": "http.request", "body": b"def", "more_body": True},
            AssertionError("must stop after the final whole ASGI event"),
        ]
    )
    await JsonBodyLimitMiddleware(app, max_characters=10)(
        http_scope([(b"content-length", b"1000")]), receive, send
    )
    assert receive.await_count == 2
    app.assert_not_awaited()
    assert send.await_args_list[0].args[0]["status"] == 413


async def test_checked_body_is_replayed_unchanged_then_disconnect_passes_through() -> (
    None
):
    receive = AsyncMock(
        side_effect=[
            {"type": "http.request", "body": b'{"x":', "more_body": True},
            {"type": "http.request", "body": b"1}", "more_body": False},
            {"type": "http.disconnect"},
        ]
    )
    messages = []

    async def app(scope, replay, send):
        messages.extend([await replay(), await replay()])

    await JsonBodyLimitMiddleware(app)(http_scope(), receive, AsyncMock())
    assert messages == [
        {"type": "http.request", "body": b'{"x":1}', "more_body": False},
        {"type": "http.disconnect"},
    ]


async def test_client_disconnect_does_not_run_application() -> None:
    app, send = AsyncMock(), AsyncMock()
    receive = AsyncMock(return_value={"type": "http.disconnect"})
    await JsonBodyLimitMiddleware(app)(http_scope(), receive, send)
    app.assert_not_awaited()
    send.assert_not_awaited()


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
async def test_non_http_scopes_pass_through(scope_type) -> None:
    app, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
    scope = {"type": scope_type}
    await JsonBodyLimitMiddleware(app)(scope, receive, send)
    app.assert_awaited_once_with(scope, receive, send)
    receive.assert_not_awaited()


async def test_non_json_media_type_passes_through() -> None:
    app, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
    scope = http_scope([(b"content-type", b"application/octet-stream")])
    await JsonBodyLimitMiddleware(app)(scope, receive, send)
    app.assert_awaited_once_with(scope, receive, send)
    receive.assert_not_awaited()


async def test_http2_error_has_no_connection_header() -> None:
    app, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
    receive.return_value = {"type": "http.disconnect"}
    await JsonBodyLimitMiddleware(app, max_characters=10)(
        http_scope([(b"content-length", b"41")], version="2"), receive, send
    )
    response = send.await_args_list[0].args[0]
    assert response["status"] == 413
    assert b"connection" not in dict(response["headers"])


async def test_rejection_does_not_wait_forever_for_stalled_body(monkeypatch) -> None:
    monkeypatch.setattr("common.middleware.json_body_limit.REJECT_DRAIN_TIMEOUT", 0.01)
    app, send = AsyncMock(), AsyncMock()
    waiting = asyncio.Event()

    async def receive():
        await waiting.wait()
        raise AssertionError("unreachable")

    await asyncio.wait_for(
        JsonBodyLimitMiddleware(app, max_characters=10)(
            http_scope([(b"content-length", b"1000")]), receive, send
        ),
        timeout=1,
    )
    app.assert_not_awaited()
    assert send.await_args_list[0].args[0]["status"] == 413
    assert send.await_args_list[-1].args[0]["type"] == "http.response.body"
    assert not send.await_args_list[-1].args[0].get("more_body", False)


async def test_empty_buffered_messages_still_respect_discard_timeout(
    monkeypatch,
) -> None:
    monkeypatch.setattr("common.middleware.json_body_limit.REJECT_DRAIN_TIMEOUT", 0.01)
    app, send = AsyncMock(), AsyncMock()
    receive = AsyncMock(
        return_value={"type": "http.request", "body": b"", "more_body": True}
    )
    await asyncio.wait_for(
        JsonBodyLimitMiddleware(app, max_characters=10)(
            http_scope([(b"content-length", b"1000")]), receive, send
        ),
        timeout=1,
    )
    app.assert_not_awaited()
    assert receive.await_count > 0


async def test_external_cancellation_during_discard_is_not_swallowed() -> None:
    app, send = AsyncMock(), AsyncMock()
    reading = asyncio.Event()

    async def receive():
        reading.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    task = asyncio.create_task(
        JsonBodyLimitMiddleware(app, max_characters=10)(
            http_scope([(b"content-length", b"1000")]), receive, send
        )
    )
    await asyncio.wait_for(reading.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    app.assert_not_awaited()


@pytest.mark.parametrize("limit", [0, -1])
def test_nonpositive_limit_is_rejected(limit) -> None:
    with pytest.raises(ValueError):
        JsonBodyLimitMiddleware(AsyncMock(), max_characters=limit)


def test_openapi_documents_body_limit_for_every_operation() -> None:
    document = create_app().openapi()
    for methods in document["paths"].values():
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            response = operation["responses"]["413"]
            assert "65536" in response["description"]
            schema = response["content"]["application/json"]["schema"]
            assert schema["properties"]["detail"]["type"] == "string"
