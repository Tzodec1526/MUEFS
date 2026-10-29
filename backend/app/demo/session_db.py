"""Per-visitor isolated SQLite sandboxes for the public hosted demo.

DEMO DEPLOY ONLY. A real court deployment uses one shared database. For the public
demo we give each browser session its own copy of a seeded template database, so
visitors never see or affect each other. When the per-session cap is reached (or a
visitor blocks cookies) they fall back to a shared, restart-reset sandbox. Each
sandbox's uploads live in its own quota-limited folder, deleted with the sandbox.

This is deliberately single-process and disk-based: the demo runs as one Render
instance, so an in-memory registry plus copied SQLite files is all it needs.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import shutil
import threading
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import anyio
from fastapi import Request
from sqlalchemy import URL, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import storage_cleanup
from app.config import settings
from app.services import document_service, storage_intent

COOKIE_NAME = "muefs_demo_sid"
SHARED_SID = "_shared"
_SWEEP_INTERVAL_SEC = 300.0

# sid -> last-access epoch seconds. In-memory, single process by design.
_last_access: dict[str, float] = {}
_last_sweep = 0.0
_session_creation_lock = threading.Lock()


def _data_dir() -> Path:
    return Path(os.getenv("DEMO_DATA_DIR", "demo_data"))


def _template_db() -> Path:
    return _data_dir() / "template.db"


def _sessions_dir() -> Path:
    return _data_dir() / "sessions"


def _session_path(sid: str) -> Path:
    return _sessions_dir() / f"{sid}.db"


def _uploads_dir() -> Path:
    return _data_dir() / "uploads"


def upload_scope(sid: str) -> document_service.LocalStorageScope:
    """The sandbox's private document folder, removed along with its database."""
    return document_service.LocalStorageScope(
        root=_uploads_dir() / sid, quota_bytes=settings.demo_storage_quota_mb * 1024 * 1024,
    )


def _is_valid_sid(sid: str) -> bool:
    return len(sid) == 32 and all(c in "0123456789abcdef" for c in sid)


def seed_template() -> None:
    """Create the seeded template database once (full Michigan seed), then (re)create
    the shared sandbox from it. Idempotent for the template; the shared copy refreshes
    on each boot, and uploads belonging to no current sandbox are removed."""
    _sessions_dir().mkdir(parents=True, exist_ok=True)
    _uploads_dir().mkdir(parents=True, exist_ok=True)
    template = _template_db()
    if not template.exists():
        from app.seed_data import seed_database

        # An interrupted first boot must not leave a schema-only template that looks ready.
        partial = template.with_suffix(".seeding")
        partial.unlink(missing_ok=True)
        seed_database(url=f"sqlite:///{partial}")
        partial.replace(template)
    else:
        from app.demo.schema import prepare_demo_schema

        for path in (template, *_sessions_dir().glob("*.db")):
            engine = create_engine(f"sqlite:///{path}")
            try:
                prepare_demo_schema(engine)
            finally:
                engine.dispose()
    shutil.copyfile(template, _session_path(SHARED_SID))
    for folder in _uploads_dir().iterdir():
        if folder.name == SHARED_SID or not _session_path(folder.name).exists():
            shutil.rmtree(folder, ignore_errors=True)


def ensure_session_db(sid: str) -> Path:
    """Return this session's SQLite path, copying the seeded template if it's new.

    At capacity a new id gets the shared sandbox. The cap is enforced here, not only
    when an id is issued, because a client can present any well-formed cookie."""
    # First-page API requests run in separate threads. Do not let one open a
    # partially copied database, or overwrite another request's committed work.
    with _session_creation_lock:
        return _ensure(sid)


def open_sandbox(sid: str) -> Path:
    """Sweep idle sandboxes, then return this request's sandbox marked as in use.

    The sweep and the lookup share one lock, so a sandbox cannot be deleted between a
    request finding it and marking it active."""
    with _session_creation_lock:
        _sweep_idle()
        path = _ensure(sid)
        if path.stem != SHARED_SID:
            touch(path.stem)
        return path


def _ensure(sid: str) -> Path:
    path = _session_path(sid)
    if not path.exists():
        if active_session_count() >= settings.demo_max_sessions:
            return _session_path(SHARED_SID)
        temporary = path.with_suffix(".tmp")
        try:
            shutil.copyfile(_template_db(), temporary)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return path


def active_session_count() -> int:
    """Number of private sandboxes (the shared one doesn't count toward the cap)."""
    return sum(1 for p in _sessions_dir().glob("*.db") if p.stem != SHARED_SID)


def resolve_sid(request: Request, *, allocate: bool = True) -> str:
    """Decide which sandbox this request uses.

    Reuse a valid existing cookie; otherwise mint a new private sandbox if under the
    cap, else fall back to the shared one. Browsers load a page before calling the
    API, so cookieless API clients (monitors, scripts) use the shared sandbox."""
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie and (cookie == SHARED_SID or _is_valid_sid(cookie)):
        return cookie
    if allocate and active_session_count() < settings.demo_max_sessions:
        return secrets.token_hex(16)
    return SHARED_SID


def touch(sid: str) -> None:
    _last_access[sid] = time.time()


def maybe_sweep() -> None:
    """Opportunistically delete idle private sandboxes — piggybacks on request traffic
    so there's no background task to manage."""
    with _session_creation_lock:
        _sweep_idle()


def _sweep_idle() -> None:
    global _last_sweep
    now = time.time()
    if now - _last_sweep < _SWEEP_INTERVAL_SEC:
        return
    _last_sweep = now
    ttl = settings.demo_session_ttl_minutes * 60
    for p in _sessions_dir().glob("*.db"):
        if p.stem == SHARED_SID:
            continue
        try:
            # After a restart, recent writes still count as activity.
            last = max(_last_access.get(p.stem, 0.0), p.stat().st_mtime)
        except FileNotFoundError:
            continue
        if now - last > ttl:
            try:
                p.unlink()
            except OSError:
                continue
            shutil.rmtree(_uploads_dir() / p.stem, ignore_errors=True)
            _last_access.pop(p.stem, None)


class DemoSessionMiddleware:
    """Pure-ASGI middleware: pin each request to a sandbox and keep private sandboxes'
    cookies current.

    API requests open their sandbox here, so the database (read by get_demo_db from the
    scope state) and the document folder belong to the same sandbox for the whole
    response, including a download streamed after the transaction ends. Pure ASGI (not
    BaseHTTPMiddleware) so scope-state and Set-Cookie propagate reliably."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "").rstrip("/")
        if (scope["type"] != "http"
                or path in {"/health", "/ready", "/config.js"}
                or path.startswith("/assets/")):
            await self.app(scope, receive, send)
            return
        api = path.startswith("/api/")
        sid = resolve_sid(Request(scope), allocate=not api)
        token = None
        if api:
            database = await asyncio.to_thread(open_sandbox, sid)
            scope.setdefault("state", {})["demo_database"] = database
            token = document_service.storage_scope.set(upload_scope(database.stem))
        try:
            await self.app(scope, receive, send if sid == SHARED_SID else _renewing(send, sid))
        finally:
            if token is not None:
                document_service.storage_scope.reset(token)


def _renewing(send: Send, sid: str) -> Send:
    # Renew on every response; a fixed expiry would end an active session mid-use.
    ttl = settings.demo_session_ttl_minutes * 60
    cookie = f"{COOKIE_NAME}={sid}; Max-Age={ttl}; Path=/; HttpOnly; SameSite=Lax".encode()

    async def send_with_cookie(message: Message) -> None:
        if message["type"] == "http.response.start":
            message.setdefault("headers", []).append((b"set-cookie", cookie))
        await send(message)

    return send_with_cookie


async def get_demo_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: a session bound to the sandbox DemoSessionMiddleware opened.

    Replaces the app's normal get_db when demo isolation is on (wired in demo.server).
    A fresh engine per request keeps the lifecycle trivial — only the files persist."""
    path = getattr(request.state, "demo_database", None) or _session_path(SHARED_SID)
    engine = create_async_engine(URL.create(
        "sqlite+aiosqlite", database=Path(path).resolve().as_uri(),
        query={"mode": "rw", "uri": "true"},
    ))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            try:
                yield session
            except BaseException:
                await storage_intent.rollback_with_upload_cleanup(session)
                raise
            try:
                await session.commit()
            except BaseException:
                await storage_intent.rollback_with_upload_cleanup(session, verify_with=factory)
                raise
        # No worker serves sandbox databases: delete removed drafts' files now, so they
        # stop counting against the sandbox's quota.
        await storage_cleanup.drain(factory)
    finally:
        with anyio.CancelScope(shield=True):
            await engine.dispose()
