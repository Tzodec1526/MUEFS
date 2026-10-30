import asyncio
import threading
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import event, select, text

from app.database import get_db
from app.main import app
from app.models.case import Case, CaseParticipant, ParticipantRole
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.services import document_service, filing_service
from tests.filing_requests import submission_review
from tests.test_filing_concurrency import POSTGRES_URL, prepare_filing
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions
from tests.test_filing_date_orders import DECISION, ORDER

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


def _position(events: list[str], matches) -> int:
    found = [index for index, item in enumerate(events) if matches(item)]
    assert found, events
    return found[0]


def _locks_account(statement: str) -> bool:
    return statement.startswith("SELECT users.") and statement.endswith("FOR SHARE")


def _locks_filing(statement: str) -> bool:
    return statement.startswith("SELECT filing_envelopes.") and statement.endswith("FOR UPDATE")


def _shared_destination(statement: str) -> str | None:
    table = statement.partition(" FROM ")[2].split(" ", 1)[0]
    if " FOR SHARE" in statement and table in ("courts", "case_types", "cases"):
        return table
    return None


async def returned_subsequent_filing(factory):
    fid, filer, clerk = await prepare_filing(factory)
    async with factory.begin() as db:
        filing = await db.get(FilingEnvelope, fid)
        case = Case(
            court_id=filing.court_id, case_type_id=filing.case_type_id,
            case_number="LOCK-ORDER-1", title="Receipt v. Order", filed_date=datetime.now(UTC),
        )
        db.add(case)
        await db.flush()
        db.add(CaseParticipant(
            case_id=case.id, user_id=filer, role=ParticipantRole.PLAINTIFF,
            party_name="Receipt Filer", access_enabled=True, reviewed_at=datetime.now(UTC),
        ))
        filing.filing_type, filing.case_id, filing.case_title = "subsequent", case.id, case.title
        await db.flush()
        assert await filing_service.submit_filing(db, fid)
        returned = await filing_service.review_filing(
            db, fid, clerk, "return", "Correct the exhibit", expected_submission_count=1,
        )
        assert returned.status == FilingStatus.RETURNED
    return fid, filer, clerk, case.id


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


async def test_resubmission_shares_no_destination_before_locking_the_filing(
    api, statements, monkeypatch,
):
    fid, filer, _clerk, _case = await returned_subsequent_filing(api)
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
    read = _position(events, lambda s: s == "storage read")
    filing = _position(events, _locks_filing)
    assert read < filing
    assert [s for s in events[:filing] if _shared_destination(s)] == []
    assert {_shared_destination(s) for s in events[filing:]} - {None} == {"courts", "cases"}


@pytest.mark.parametrize("table", ["cases", "courts", "case_types"])
async def test_a_slow_storage_read_leaves_the_resubmitted_destination_unlocked(
    api, monkeypatch, table,
):
    fid, filer, _clerk, case_id = await returned_subsequent_filing(api)
    async with api() as db:
        filing = await db.get(FilingEnvelope, fid)
        target = {"cases": case_id, "courts": filing.court_id,
                  "case_types": filing.case_type_id}[table]
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
                    text(f"SELECT id FROM {table} WHERE id = :id FOR UPDATE NOWAIT"),
                    {"id": target},
                )
        finally:
            release.set()
            submitted = await pending
    assert submitted.status_code == 200, submitted.text


async def test_resubmission_and_a_case_date_order_on_the_same_filing_both_finish(
    postgres_sessions, monkeypatch,
):
    fid, filer, clerk, case_id = await returned_subsequent_filing(postgres_sessions)
    started, release = threading.Event(), threading.Event()
    integrity = document_service.stored_integrity

    def slow_integrity(file_key):
        started.set()
        assert release.wait(10), "Test did not release the storage read"
        return integrity(file_key)

    monkeypatch.setattr(document_service, "stored_integrity", slow_integrity)
    order_pid = None

    async def sessions(request: Request):
        nonlocal order_pid
        async with postgres_sessions.begin() as db:
            if request.method == "POST" and request.url.path.endswith("/filing-date"):
                order_pid = await db.scalar(text("SELECT pg_backend_pid()"))
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, sessions)
    url = f"/api/v1/clerk/filings/{fid}/filing-date"
    as_filer, as_clerk = {"X-Demo-User-Id": str(filer)}, {"X-Demo-User-Id": str(clerk)}
    pending = []
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        state = (await client.get(url, headers=as_clerk)).json()
        client.headers.update(as_filer)
        review = await submission_review(client, fid)
        try:
            pending.append(asyncio.create_task(client.post(
                f"/api/v1/filings/{fid}/submit", json=review, headers=as_filer,
            )))
            assert await asyncio.to_thread(started.wait, 5)
            order = asyncio.create_task(client.post(url, headers=as_clerk, data={
                **DECISION, "expected_version": str(state["version"]), "update_case_date": "true",
                "expected_case_version": str(state["case_date_version"]),
            }, files={"file": ("order.pdf", ORDER, "application/pdf")}))
            pending.append(order)
            async with asyncio.timeout(10), postgres_sessions() as observer:
                while not order.done() and await observer.scalar(text(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid",
                ), {"pid": order_pid}) != "Lock":
                    await asyncio.sleep(0.01)
        finally:
            release.set()
            outcomes = await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), 15)
    returned = [
        (o.status_code, o.text[:200]) if isinstance(o, Response) else repr(o) for o in outcomes
    ]
    assert [o.status_code if isinstance(o, Response) else None for o in outcomes] == [200, 201], (
        returned
    )
    async with postgres_sessions() as db:
        filing = await db.get(FilingEnvelope, fid)
        case = await db.get(Case, case_id)
        events = (await db.execute(
            select(FilingTransaction.event_type, FilingTransaction.submission_number)
            .where(FilingTransaction.filing_id == fid)
        )).tuples().all()
    assert filing.status == FilingStatus.SUBMITTED and filing.submission_count == 2
    assert filing.filing_date_version == state["version"] + 2
    assert case.filing_date == date(2026, 9, 3) and case.filing_date_version == 1
    assert sorted(events) == [
        ("filing_date_ordered", 1), ("returned", 1), ("submitted", 1), ("submitted", 2),
    ]
