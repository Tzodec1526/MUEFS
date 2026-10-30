import asyncio
import threading
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select

from app.database import get_db
from app.main import app
from app.models.filing import FilingEnvelope
from app.services import document_service
from tests.filing_requests import submission_review
from tests.test_filing_concurrency import POSTGRES_URL, prepare_filing
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


def _position(events: list[str], matches) -> int:
    found = [index for index, item in enumerate(events) if matches(item)]
    assert found, events
    return found[0]


def _locks_account(statement: str) -> bool:
    return statement.startswith("SELECT users.") and statement.endswith("FOR SHARE")


def _locks_filing(statement: str) -> bool:
    return statement.startswith("SELECT filing_envelopes.") and statement.endswith("FOR UPDATE")


@pytest.fixture
def api(postgres_sessions):
    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    yield postgres_sessions
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def statements(postgres_sessions):
    events: list[str] = []
    engine = postgres_sessions.kw["bind"].sync_engine

    def record(conn, cursor, statement, parameters, context, executemany):
        events.append(" ".join(statement.split()))

    yield events, lambda: event.listen(engine, "before_cursor_execute", record)
    if event.contains(engine, "before_cursor_execute", record):
        event.remove(engine, "before_cursor_execute", record)


async def test_upload_locks_the_account_then_the_filing_before_inserting_the_document(
    api, statements,
):
    fid, filer, _clerk = await prepare_filing(api)
    events, start = statements
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test",
                           headers={"X-Demo-User-Id": str(filer)}) as client:
        start()
        response = await client.post(
            f"/api/v1/filings/{fid}/documents",
            headers={"Idempotency-Key": str(uuid4())},
            data={"title": "Exhibit", "document_type_code": "EXHIBIT"},
            files={"file": ("exhibit.txt", b"Synthetic exhibit", "text/plain")},
        )
    assert response.status_code == 200, response.text
    account = _position(events, _locks_account)
    filing = _position(events, _locks_filing)
    insert = _position(events, lambda s: s.startswith("INSERT INTO "))
    assert account < filing < insert
    assert events[insert].startswith("INSERT INTO filing_documents ")


async def test_submission_reads_storage_before_locking_the_filing(api, statements, monkeypatch):
    fid, filer, _clerk = await prepare_filing(api)
    events, start = statements
    integrity = document_service.stored_integrity

    def observed_integrity(file_key):
        events.append("storage read")
        return integrity(file_key)

    monkeypatch.setattr(document_service, "stored_integrity", observed_integrity)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test",
                           headers={"X-Demo-User-Id": str(filer)}) as client:
        review = await submission_review(client, fid)
        start()
        response = await client.post(f"/api/v1/filings/{fid}/submit", json=review)
    assert response.status_code == 200, response.text
    account = _position(events, _locks_account)
    read = _position(events, lambda s: s == "storage read")
    filing = _position(events, _locks_filing)
    assert account < read < filing
    assert events.count("storage read") == 1


async def test_a_slow_storage_read_leaves_the_filing_unlocked(api, monkeypatch):
    fid, filer, _clerk = await prepare_filing(api)
    started, release = threading.Event(), threading.Event()
    integrity = document_service.stored_integrity

    def slow_integrity(file_key):
        started.set()
        assert release.wait(10), "Test did not release the storage read"
        return integrity(file_key)

    monkeypatch.setattr(document_service, "stored_integrity", slow_integrity)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test",
                           headers={"X-Demo-User-Id": str(filer)}) as client:
        pending = asyncio.create_task(client.post(
            f"/api/v1/filings/{fid}/submit", json=await submission_review(client, fid),
        ))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            async with api.begin() as other:
                await other.execute(
                    select(FilingEnvelope.id).where(FilingEnvelope.id == fid)
                    .with_for_update(nowait=True)
                )
        finally:
            release.set()
            submitted = await pending
    assert submitted.status_code == 200, submitted.text
