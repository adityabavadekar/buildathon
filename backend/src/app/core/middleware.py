"""Pure-ASGI middleware.

Hand-rolled rather than using ``asgi-correlation-id`` for one specific reason:
that library's default validator silently discards an incoming request ID that
is not a UUID and mints a fresh one, which severs the trace to whatever upstream
sent it. For an audit trail, an unfamiliar-but-present ID is more useful than a
new one, so incoming IDs are preserved (sanitised, not replaced).

Pure ASGI rather than ``BaseHTTPMiddleware`` because the latter runs the endpoint
in a child task, which breaks ``contextvars`` propagation back to the caller.
"""

import re
import uuid
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = b"x-request-id"
_MAX_REQUEST_ID_LENGTH = 128
# Incoming IDs are untrusted input: keep only characters safe to put in a log
# line and echo back in a header.
_UNSAFE_CHARS = re.compile(rb"[^A-Za-z0-9._:-]")


def _sanitise(raw: bytes) -> str | None:
    cleaned = _UNSAFE_CHARS.sub(b"", raw)[:_MAX_REQUEST_ID_LENGTH]
    return cleaned.decode("ascii") if cleaned else None


class RequestIDMiddleware:
    """Bind a request ID to the logging context and echo it in the response."""

    def __init__(self, app: "ASGIApp") -> None:
        self.app = app

    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers") or []).get(REQUEST_ID_HEADER)
        request_id = (_sanitise(incoming) if incoming else None) or uuid.uuid4().hex

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=scope.get("method"),
            path=scope.get("path"),
        )

        async def send_with_request_id(message: "Message") -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((REQUEST_ID_HEADER, request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            structlog.contextvars.clear_contextvars()
