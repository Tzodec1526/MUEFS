"""FastAPI app for the public hosted demo.

One container serves the API and the built React SPA from the same origin, and every
browser session gets its own isolated, seeded SQLite sandbox. Run with:

    uvicorn app.demo.server:app

Importing this module extends the core app (app.main) with the demo's session
middleware, database override and SPA routes.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.database import get_db
from app.demo import session_db
from app.main import app

# Seed the template database once, before the server takes traffic.
session_db.seed_template()
app.state.readiness_engine = create_async_engine(URL.create(
    "sqlite+aiosqlite", database=session_db._template_db().resolve().as_uri(),
    query={"mode": "ro", "uri": "true"},
))

# Every visitor gets their own sandbox instead of the single global database.
app.dependency_overrides[get_db] = session_db.get_demo_db
app.add_middleware(session_db.DemoSessionMiddleware)

_STATIC_ROOT = Path(settings.demo_static_dir).resolve()
mimetypes.add_type("font/woff2", ".woff2")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str) -> FileResponse:
    """Serve the built SPA — a real static file if one exists, else index.html so
    client-side routes (e.g. /cases/search) survive a refresh. API and docs paths
    are handled by earlier routes; anything else under them 404s rather than serving HTML."""
    if full_path.startswith(("api/", "docs", "redoc", "openapi", "health", "ready", "config.js")):
        raise HTTPException(status_code=404)
    candidate = (_STATIC_ROOT / full_path).resolve()
    if full_path and candidate.is_file() and candidate.is_relative_to(_STATIC_ROOT):
        # Vite emits content-hashed bundles in assets/. HTML must always fetch the
        # current filenames after a deployment instead of reusing a stale index.
        cache = (
            "public, max-age=31536000, immutable"
            if full_path.startswith("assets/") else "no-cache"
        )
        if candidate.name == "index.html":
            cache = "no-store"
        return FileResponse(candidate, headers={"Cache-Control": cache})
    if full_path.startswith("assets/"):
        # A missing old bundle must be a real 404, not HTML with a JavaScript MIME error.
        raise HTTPException(status_code=404)
    index = _STATIC_ROOT / "index.html"
    if index.is_file():
        return FileResponse(index, headers={"Cache-Control": "no-store"})
    raise HTTPException(status_code=404)
