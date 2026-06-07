"""FastAPI app for the public hosted demo.

One container serves the API and the built React SPA from the same origin, and every
browser session gets its own isolated, seeded SQLite sandbox. Run with:

    uvicorn app.demo.server:app

The core app (app.main) is untouched; this module wraps it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.database import get_db
from app.demo import session_db
from app.main import app

# Seed the template database once, before the server takes traffic.
session_db.seed_template()

# Every visitor gets their own sandbox instead of the single global database.
app.dependency_overrides[get_db] = session_db.get_demo_db

_STATIC_ROOT = Path(settings.demo_static_dir).resolve()


class DemoSessionMiddleware:
    """Pure-ASGI middleware: pin each request to a sandbox id (written into scope
    state, where get_demo_db reads it) and set the cookie for new private sandboxes.

    Pure ASGI (not BaseHTTPMiddleware) so scope-state and Set-Cookie propagate reliably."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        sid, set_cookie = session_db.resolve_sid(Request(scope))
        scope.setdefault("state", {})["demo_sid"] = sid
        session_db.touch(sid)
        session_db.maybe_sweep()
        if not set_cookie:
            await self.app(scope, receive, send)
            return
        ttl = settings.demo_session_ttl_minutes * 60
        cookie = (
            f"{session_db.COOKIE_NAME}={sid}; Max-Age={ttl}; Path=/; HttpOnly; SameSite=Lax"
        ).encode()

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"set-cookie", cookie))
            await send(message)

        await self.app(scope, receive, send_with_cookie)


app.add_middleware(DemoSessionMiddleware)


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str) -> FileResponse:
    """Serve the built SPA — a real static file if one exists, else index.html so
    client-side routes (e.g. /cases/search) survive a refresh. API and docs paths
    are handled by earlier routes; anything else under them 404s rather than serving HTML."""
    if full_path.startswith(("api/", "docs", "redoc", "openapi", "health")):
        raise HTTPException(status_code=404)
    candidate = (_STATIC_ROOT / full_path).resolve()
    if full_path and candidate.is_file() and candidate.is_relative_to(_STATIC_ROOT):
        return FileResponse(candidate)
    index = _STATIC_ROOT / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404)
