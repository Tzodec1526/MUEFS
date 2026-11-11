from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.middleware import Middleware

from app.config import settings
from app.database import get_db
from app.demo import session_db
from app.main import app
from app.middleware.rate_limit import RateLimitMiddleware

session_db.seed_template()
app.state.readiness_engine = create_async_engine(URL.create(
    "sqlite+aiosqlite", database=session_db._template_db().resolve().as_uri(),
    query={"mode": "ro", "uri": "true"},
))

app.dependency_overrides[get_db] = session_db.get_demo_db
_rate_limit = next(
    index for index, entry in enumerate(app.user_middleware) if entry.cls is RateLimitMiddleware
)
app.user_middleware.insert(_rate_limit + 1, Middleware(session_db.DemoSessionMiddleware))

_STATIC_ROOT = Path(settings.demo_static_dir).resolve()
mimetypes.add_type("font/woff2", ".woff2")


def _accepts_gzip(accept_encoding: str) -> bool:
    for coding in accept_encoding.lower().split(","):
        name, _, parameters = coding.partition(";")
        if name.strip() == "gzip":
            return re.fullmatch(r"q=0(\.0*)?", parameters.replace(" ", "")) is None
    return False


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(request: Request, full_path: str) -> FileResponse:
    if full_path.startswith(("api/", "docs", "redoc", "openapi", "health", "ready", "config.js")):
        raise HTTPException(status_code=404)
    candidate = (_STATIC_ROOT / full_path).resolve()
    if (
        full_path and candidate.is_file() and candidate.is_relative_to(_STATIC_ROOT)
        and candidate.suffix != ".gz"
    ):
        cache = (
            "public, max-age=31536000, immutable"
            if full_path.startswith("assets/") else "no-cache"
        )
        if candidate.name == "index.html":
            cache = "no-store"
        headers = {"Cache-Control": cache}
        compressed = candidate.with_name(f"{candidate.name}.gz")
        if compressed.is_file():
            headers["Vary"] = "Accept-Encoding"
            if _accepts_gzip(request.headers.get("accept-encoding", "")):
                headers["Content-Encoding"] = "gzip"
                return FileResponse(compressed, headers=headers)
        return FileResponse(candidate, headers=headers)
    if full_path.startswith("assets/"):
        raise HTTPException(status_code=404)
    index = _STATIC_ROOT / "index.html"
    if index.is_file():
        return FileResponse(index, headers={"Cache-Control": "no-store"})
    raise HTTPException(status_code=404)
