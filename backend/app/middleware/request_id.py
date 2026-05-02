"""Attach a request ID to every response for traceability.

If the client supplies ``X-Request-ID``, we honor it (sanitized to avoid header
injection); otherwise we mint a fresh UUID4. The id is also stashed on
``request.state.request_id`` and on a contextvar consumed by ``logging_config`` so log
records emitted during the request — even from deeply-nested helpers — surface it.
"""

from __future__ import annotations

import re
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.logging_config import set_request_id

_HEADER_NAME = "X-Request-ID"
_VALID_ID = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")


def _sanitize(raw: str | None) -> str:
    if raw and _VALID_ID.match(raw):
        return raw
    return uuid.uuid4().hex


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = _sanitize(request.headers.get(_HEADER_NAME))
        request.state.request_id = request_id
        # contextvars are task-local, so the next request starts with the default again.
        set_request_id(request_id)
        response = await call_next(request)
        response.headers[_HEADER_NAME] = request_id
        return response
