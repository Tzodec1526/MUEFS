from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings

_OVERHEAD_BYTES = 1024 * 1024
_DETAIL = "Request body too large"


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        limit = _OVERHEAD_BYTES
        if headers.get(b"content-type", b"").lower().startswith(b"multipart/form-data"):
            limit += settings.max_file_size_mb * 1024 * 1024
        declared = headers.get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await JSONResponse({"detail": _DETAIL}, status_code=413)(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail=_DETAIL)
            return message

        await self.app(scope, limited_receive, send)
