from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


TOKEN_PATTERNS = (
    re.compile(r"(OAuth\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"(access_token=)[^&#\s]+", re.IGNORECASE),
)

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
CSRF_HEADER = "x-local-yandex-disk"


def redact_secrets(value: object) -> str:
    text = str(value)
    for pattern in TOKEN_PATTERNS:
        text = pattern.sub(r"\1[redacted]", text)
    text = re.sub(r"(?i)(authorization\s*[:=]\s*)[^\s,;]+", r"\1[redacted]", text)
    return text


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secrets(record.getMessage())
        record.args = ()
        return True


def configure_safe_logging() -> None:
    redaction_filter = SecretRedactionFilter()
    for logger_name in ("", "uvicorn", "uvicorn.error", "httpx", "httpcore"):
        logger = logging.getLogger(logger_name)
        logger.addFilter(redaction_filter)


def _host_without_port(value: str) -> str:
    if value.startswith("[::1]"):
        return "[::1]"
    if value.count(":") == 1:
        return value.rsplit(":", 1)[0]
    return value


def _is_local_client(scope: Scope) -> bool:
    client = scope.get("client")
    if not client:
        return True
    host = client[0]
    return host in {"127.0.0.1", "::1"} or host.startswith("127.")


def _is_local_host_header(headers: Headers) -> bool:
    host = headers.get("host", "")
    if not host:
        return False
    return _host_without_port(host.lower()) in LOCAL_HOSTS


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if not _is_local_client(scope) or not _is_local_host_header(headers):
            await JSONResponse({"detail": "This application accepts local requests only."}, status_code=403)(
                scope, receive, send
            )
            return

        await self.app(scope, receive, send)


class LocalAPIMutationHeaderMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")
        if method in {"POST", "PUT", "PATCH", "DELETE"} and path.startswith("/api/"):
            headers = Headers(scope=scope)
            if headers.get(CSRF_HEADER) != "1":
                await JSONResponse({"detail": "Missing local API header."}, status_code=403)(scope, receive, send)
                return

        await self.app(scope, receive, send)


Handler = Callable[[Scope, Receive, Send], Awaitable[None]]
