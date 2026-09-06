"""Test configuration and fixtures."""

import hashlib
import os
from uuid import uuid4

# Before any app.settings load: pin the test environment to demo mode (SQLite + local
# document storage) so tests never reach for Postgres / Redis / S3. This mirrors how the
# hosted demo actually runs. setdefault leaves an explicit DATABASE_URL (e.g. a CI matrix
# value) untouched.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("ALLOW_DEMO_MODE", "true")

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import *  # noqa: F401, F403

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
def stored_document(monkeypatch, tmp_path):
    from app.models.filing import FilingDocument
    from app.services import document_service

    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)

    def create(envelope_id, *, document_type_code="COMPLAINT", title="Complaint"):
        content = f"Synthetic {title}".encode()
        key = f"tests/{uuid4()}.txt"
        document_service.upload_document(content, key, "text/plain")
        return FilingDocument(
            envelope_id=envelope_id, document_type_code=document_type_code, title=title,
            file_key=key, file_size_bytes=len(content), mime_type="text/plain",
            sha256_hash=hashlib.sha256(content).hexdigest(), pii_warnings=[],
        )

    return create


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
