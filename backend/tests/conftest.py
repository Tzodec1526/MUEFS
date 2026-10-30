"""Test configuration and fixtures."""

import hashlib
import os
import re
from uuid import uuid4

# Before any app.settings load: pin the test environment to demo mode (SQLite + local
# document storage) so tests never reach for Postgres / Redis / S3. This mirrors how the
# hosted demo actually runs. Assign rather than default: a DATABASE_URL exported for the
# app must not send test uploads to a real bucket. Service-backed tests opt in through
# MUEFS_TEST_* variables instead.
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["DEBUG"] = "true"
os.environ["ALLOW_DEMO_MODE"] = "true"

from collections.abc import AsyncGenerator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import User

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
        await conn.run_sync(User.metadata.create_all)

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


_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
_UTC_OFFSET = re.compile(r"(?:Z|[+-]\d{2}:\d{2})$")
_checked_timestamps: list[int] = []


def _timestamps(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for item in value.values():
            yield from _timestamps(item)
    elif isinstance(value, list):
        for item in value:
            yield from _timestamps(item)
    elif isinstance(value, str) and _TIMESTAMP.match(value):
        yield value


@pytest.fixture(autouse=True)
def api_timestamps_carry_a_utc_offset(monkeypatch):
    from httpx import AsyncClient

    send = AsyncClient.send
    naive: list[str] = []

    async def checked_send(self, request, **kwargs):
        response = await send(self, request, **kwargs)
        if (
            request.url.path.startswith("/api/")
            and response.is_success
            and response.headers.get("content-type", "").startswith("application/json")
            and await response.aread()
        ):
            stamps = list(_timestamps(response.json()))
            _checked_timestamps.append(len(stamps))
            naive.extend(
                f"{request.method} {request.url.path}: {stamp}"
                for stamp in stamps if not _UTC_OFFSET.search(stamp)
            )
        return response

    monkeypatch.setattr(AsyncClient, "send", checked_send)
    yield
    assert not naive, naive


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(
        f"API timestamps checked for a UTC offset: {sum(_checked_timestamps)} "
        f"in {len(_checked_timestamps)} JSON responses"
    )
