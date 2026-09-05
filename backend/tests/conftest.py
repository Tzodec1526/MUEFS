"""Test configuration and fixtures."""

import os

# Before any app.settings load: pin the test environment to demo mode (SQLite + local
# document storage) so tests never reach for Postgres / Redis / S3. This mirrors how the
# hosted demo actually runs. setdefault leaves an explicit DATABASE_URL (e.g. a CI matrix
# value) untouched.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("ALLOW_DEMO_MODE", "true")

from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import *  # noqa: F401, F403

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()  # Disposing the in-memory DB also drops its tables.


@pytest_asyncio.fixture
async def api_client(db_session):
    from httpx import ASGITransport, AsyncClient

    from app.database import get_db
    from app.main import app

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
