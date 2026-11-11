from __future__ import annotations

import asyncio
import os
import secrets
import shutil
import threading
import time
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import URL, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.database import session_scope
from app.services import document_service

COOKIE_NAME = "muefs_demo_sid"
_SWEEP_INTERVAL_SEC = 300.0
_NO_SESSION = "This demo needs a session cookie. Reload the page to start a new demo session."
_AT_CAPACITY = "The demo is at capacity. Try again in a few minutes."


class DemoCapacityError(Exception):
    pass

_last_access: dict[str, float] = {}
_last_sweep = 0.0
_session_creation_lock = threading.Lock()
_engines: dict[str, async_sessionmaker[AsyncSession]] = {}


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
    return document_service.LocalStorageScope(
        root=_uploads_dir() / sid, quota_bytes=settings.demo_storage_quota_mb * 1024 * 1024,
    )


def _is_valid_sid(sid: str) -> bool:
    return len(sid) == 32 and all(c in "0123456789abcdef" for c in sid)


def seed_template() -> None:
    _sessions_dir().mkdir(parents=True, exist_ok=True)
    _uploads_dir().mkdir(parents=True, exist_ok=True)
    template = _template_db()
    if not template.exists():
        from app.seed_data import seed_database

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
    for folder in _uploads_dir().iterdir():
        if not _session_path(folder.name).exists():
            shutil.rmtree(folder, ignore_errors=True)


def open_sandbox(sid: str) -> Path:
    with _session_creation_lock:
        _sweep_idle()
        path = _ensure(sid)
        touch(sid)
        return path


def _ensure(sid: str) -> Path:
    path = _session_path(sid)
    if not path.exists():
        if active_session_count() >= settings.demo_max_sessions:
            raise DemoCapacityError(_AT_CAPACITY)
        temporary = path.with_suffix(".tmp")
        try:
            shutil.copyfile(_template_db(), temporary)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return path


def active_session_count() -> int:
    return sum(1 for _ in _sessions_dir().glob("*.db"))


def resolve_sid(request: Request, *, allocate: bool = True) -> str | None:
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie and _is_valid_sid(cookie):
        return cookie
    return secrets.token_hex(16) if allocate else None


def touch(sid: str) -> None:
    _last_access[sid] = time.time()


def _sweep_idle() -> None:
    global _last_sweep
    now = time.time()
    if now - _last_sweep < _SWEEP_INTERVAL_SEC:
        return
    _last_sweep = now
    ttl = settings.demo_session_ttl_minutes * 60
    for p in _sessions_dir().glob("*.db"):
        try:
            last = max(_last_access.get(p.stem, 0.0), p.stat().st_mtime)
        except FileNotFoundError:
            continue
        if now - last > ttl:
            try:
                p.unlink()
            except OSError:
                continue
            _engines.pop(str(p.resolve()), None)
            shutil.rmtree(_uploads_dir() / p.stem, ignore_errors=True)
            _last_access.pop(p.stem, None)


class DemoSessionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "").rstrip("/")
        if (scope["type"] != "http"
                or path in {"/health", "/ready", "/config.js"}
                or path.startswith("/assets/")):
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        api = path.startswith("/api/")
        sid = resolve_sid(request, allocate=not api)
        if sid is None:
            await JSONResponse({"detail": _NO_SESSION}, status_code=401)(scope, receive, send)
            return
        token = None
        if api:
            try:
                database = await asyncio.to_thread(open_sandbox, sid)
            except DemoCapacityError:
                refusal = JSONResponse(
                    {"detail": _AT_CAPACITY}, status_code=503, headers={"Retry-After": "300"},
                )
                await refusal(scope, receive, send)
                return
            scope.setdefault("state", {})["demo_database"] = database
            token = document_service.storage_scope.set(upload_scope(sid))
        try:
            await self.app(scope, receive, _renewing(send, sid, secure=_over_https(request)))
        finally:
            if token is not None:
                document_service.storage_scope.reset(token)


def _over_https(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


def _renewing(send: Send, sid: str, *, secure: bool) -> Send:
    ttl = settings.demo_session_ttl_minutes * 60
    attributes = f"Max-Age={ttl}; Path=/; HttpOnly; SameSite=Lax{'; Secure' if secure else ''}"
    cookie = f"{COOKIE_NAME}={sid}; {attributes}".encode()

    async def send_with_cookie(message: Message) -> None:
        if message["type"] == "http.response.start":
            message.setdefault("headers", []).append((b"set-cookie", cookie))
        await send(message)

    return send_with_cookie


def _sandbox_sessions(path: Path) -> async_sessionmaker[AsyncSession]:
    key = str(path.resolve())
    sessions = _engines.get(key)
    if sessions is None:
        engine = create_async_engine(URL.create(
            "sqlite+aiosqlite", database=path.resolve().as_uri(),
            query={"mode": "rw", "uri": "true"},
        ), poolclass=NullPool)
        sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        _engines[key] = sessions
    return sessions


async def get_demo_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    path = getattr(request.state, "demo_database", None)
    if path is None:
        raise RuntimeError("Demo API request reached the database without a sandbox")
    async with session_scope(_sandbox_sessions(Path(path)), drain=True) as session:
        yield session
