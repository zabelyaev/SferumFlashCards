import asyncio
import codecs
from functools import partial
from typing import TYPE_CHECKING

from starlette.datastructures import Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import Sequence

    from starlette.types import ASGIApp, Message, Receive, Scope, Send


MAX_JSON_BODY_CHARACTERS = 65_536
REJECT_DRAIN_BUDGET_BYTES = 8 * 1024 * 1024
REJECT_DRAIN_TIMEOUT = 1.0


class JsonBodyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        max_characters: int = MAX_JSON_BODY_CHARACTERS,
        *,
        cors_origins: Sequence[str] | None = None,
    ) -> None:
        if max_characters < 1:
            raise ValueError("JSON body character limit must be positive.")
        self.app = app
        self._max_characters = max_characters

        self._max_bytes = max_characters * 4

        self._error_cors = (
            CORSMiddleware(app, allow_origins=cors_origins, allow_credentials=False)
            if cors_origins is not None
            else None
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()

        if media_type and not (
            media_type == "application/json"
            or (media_type.startswith("application/") and media_type.endswith("+json"))
        ):
            await self.app(scope, receive, send)
            return

        try:
            content_length = int(headers.get("content-length", "0"))
        except ValueError:
            content_length = 0
        if content_length > self._max_bytes:
            await self._reject(scope, receive, send, 413, more_body=True)
            return

        decoder = codecs.getincrementaldecoder("utf-8")()
        body = bytearray()
        characters = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            more_body = message.get("more_body", False)
            if len(body) + len(chunk) > self._max_bytes:
                await self._reject(scope, receive, send, 413, more_body=more_body)
                return
            try:
                characters += len(decoder.decode(chunk, final=not more_body))
            except UnicodeDecodeError:
                await self._reject(scope, receive, send, 400, more_body=more_body)
                return
            if characters > self._max_characters:
                await self._reject(scope, receive, send, 413, more_body=more_body)
                return
            body.extend(chunk)
            if not more_body:
                break

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        status: int,
        *,
        more_body: bool,
    ) -> None:
        detail = (
            f"JSON body must not exceed {self._max_characters} characters."
            if status == 413
            else "JSON body must be valid UTF-8."
        )

        headers = (
            {"Connection": "close"}
            if scope.get("http_version", "1.1").startswith("1.")
            else None
        )
        response = JSONResponse({"detail": detail}, status_code=status, headers=headers)
        error_send = send
        request_headers = Headers(scope=scope)
        if self._error_cors is not None and "origin" in request_headers:
            error_send = partial(
                self._error_cors.send, send=send, request_headers=request_headers
            )

        async def finish_after_drain(message: Message) -> None:
            if message["type"] == "http.response.body" and more_body:
                await error_send({**message, "more_body": True})
                await self._discard_remainder(receive)
                await error_send({"type": "http.response.body", "body": b""})
            else:
                await error_send(message)

        await response(scope, receive, finish_after_drain)

    @staticmethod
    async def _discard_remainder(receive: Receive) -> None:

        remaining = REJECT_DRAIN_BUDGET_BYTES
        try:
            async with asyncio.timeout(REJECT_DRAIN_TIMEOUT):
                while remaining > 0:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    remaining -= len(message.get("body", b""))
                    if not message.get("more_body", False):
                        return

                    await asyncio.sleep(0)
        except TimeoutError:
            return
