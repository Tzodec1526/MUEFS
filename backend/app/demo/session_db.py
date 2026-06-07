"""Per-visitor isolated SQLite sandboxes for the public hosted demo.

DEMO DEPLOY ONLY. A real court deployment uses one shared database. For the public
demo we give each browser session its own copy of a seeded template database, so
visitors never see or affect each other. When the per-session cap is reached (or a
visitor blocks cookies) they fall back to a shared, restart-reset sandbox.

This is deliberately single-process and disk-based: the demo runs as one Render
instance, so an in-memory registry plus copied SQLite files is all it needs.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import shutil
import time
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

COOKIE_NAME = "muefs_demo_sid"
SHARED_SID = "_shared"
_SWEEP_INTERVAL_SEC = 300.0

# sid -> last-access epoch seconds. In-memory, single process by design.
_last_access: dict[str, float] = {}
_last_sweep = 0.0


def _data_dir() -> Path:
    return Path(os.getenv("DEMO_DATA_DIR", "demo_data"))


def _template_db() -> Path:
    return _data_dir() / "template.db"


def _sessions_dir() -> Path:
    return _data_dir() / "sessions"


def _session_path(sid: str) -> Path:
    return _sessions_dir() / f"{sid}.db"


def _is_valid_sid(sid: str) -> bool:
    return len(sid) == 32 and all(c in "0123456789abcdef" for c in sid)


def seed_template() -> None:
    """Create the seeded template database once (full Michigan seed), then (re)create
    the shared sandbox from it. Idempotent for the template; the shared copy refreshes
    on each boot."""
    _sessions_dir().mkdir(parents=True, exist_ok=True)
    template = _template_db()
    if not template.exists():
        # seed_database() reads its sync engine URL from the module global DATABASE_URL.
        os.environ["DATABASE_URL_SYNC"] = f"sqlite:///{template}"
        import app.seed_data as seed_data

        seed_data.DATABASE_URL = f"sqlite:///{template}"
        seed_data.seed_database()
    shutil.copyfile(template, _session_path(SHARED_SID))


def ensure_session_db(sid: str) -> Path:
    """Return this session's SQLite path, copying the seeded template if it's new."""
    path = _session_path(sid)
    if not path.exists():
        shutil.copyfile(_template_db(), path)
    return path


def active_session_count() -> int:
    """Number of private sandboxes (the shared one doesn't count toward the cap)."""
    return sum(1 for p in _sessions_dir().glob("*.db") if p.stem != SHARED_SID)


def resolve_sid(request: Request) -> tuple[str, bool]:
    """Decide which sandbox this request uses; returns (sid, should_set_cookie).

    Reuse a valid existing cookie; otherwise mint a new private sandbox if under the
    cap, else fall back to the shared one."""
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie and (cookie == SHARED_SID or _is_valid_sid(cookie)):
        return cookie, False
    if active_session_count() < settings.demo_max_sessions:
        return secrets.token_hex(16), True
    return SHARED_SID, False


def touch(sid: str) -> None:
    _last_access[sid] = time.time()


def maybe_sweep() -> None:
    """Opportunistically delete idle private sandboxes — piggybacks on request traffic
    so there's no background task to manage."""
    global _last_sweep
    now = time.time()
    if now - _last_sweep < _SWEEP_INTERVAL_SEC:
        return
    _last_sweep = now
    ttl = settings.demo_session_ttl_minutes * 60
    for p in _sessions_dir().glob("*.db"):
        if p.stem == SHARED_SID:
            continue
        last = _last_access.get(p.stem)
        if last is None or now - last > ttl:
            try:
                p.unlink()
            except OSError:
                pass
            _last_access.pop(p.stem, None)


async def get_demo_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: a session bound to this visitor's private SQLite sandbox.

    Replaces the app's normal get_db when demo isolation is on (wired in demo.server).
    A fresh engine per request keeps the lifecycle trivial — only the files persist."""
    sid = getattr(request.state, "demo_sid", None) or SHARED_SID
    path = await asyncio.to_thread(ensure_session_db, sid)
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()
