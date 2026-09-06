"""Exercise access decisions and retention against real PostgreSQL transactions."""

import asyncio
import threading

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError

from app.database import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.filing import FilingDocument, FilingEnvelope
from app.models.filing_transaction import FilingTransaction
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import document_service
from tests.test_document_publication import prepare_copy
from tests.test_filing_concurrency import POSTGRES_URL, prepare_filing
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest.fixture
async def court_document(postgres_sessions, monkeypatch, tmp_path):
    fid, filer, clerk = await prepare_filing(postgres_sessions)
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    async with postgres_sessions.begin() as db:
        doc = await db.scalar(select(FilingDocument).where(FilingDocument.envelope_id == fid))
        filing = await db.get(FilingEnvelope, fid)
        second = User(
            email="second@records.test",
            first_name="Second",
            last_name="Clerk",
            user_type=UserType.CLERK,
        )
        db.add(second)
        await db.flush()
        db.add(UserCourtRole(user_id=second.id, court_id=filing.court_id, role=CourtRole.CLERK))
        did, second_id = doc.id, second.id

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            client.headers["X-Demo-User-Id"] = str(filer)
            assert (await client.post(f"/api/v1/filings/{fid}/submit")).status_code == 200
            client.headers["X-Demo-User-Id"] = str(clerk)
            assert (
                await client.post(f"/api/v1/clerk/filings/{fid}/review", json={"action": "accept"})
            ).status_code == 200
            copy, _ = await prepare_copy(client, did)
            yield client, did, clerk, second_id, copy
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("postgres_sessions", [False, True], indirect=True)
async def test_competing_access_decisions_and_retained_copy(postgres_sessions, court_document):
    client, did, _, second, copy = court_document
    results = await asyncio.gather(
        client.post(
            f"/api/v1/clerk/documents/{did}/publication",
            json={
                "copy_id": copy["id"],
                "reviewed": True,
                "expected_version": 0,
                "reason": "Reviewed for publication",
            },
        ),
        client.post(
            f"/api/v1/clerk/documents/{did}/withhold",
            headers={"X-Demo-User-Id": str(second)},
            json={"expected_version": 0, "reason": "Review still pending"},
        ),
    )
    assert sorted(row.status_code for row in results) == [200, 409]
    async with postgres_sessions() as db:
        doc = await db.get(FilingDocument, did)
        assert doc.is_confidential and doc.access_version == 1
        assert doc.public_copy_id == (copy["id"] if results[0].status_code == 200 else None)
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action.in_(["public_copy.published", "document.withheld"]))
            )
            == 1
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(FilingTransaction)
                .where(
                    FilingTransaction.event_type.in_(["public_copy_published", "document_withheld"])
                )
            )
            == 1
        )
    for sql in [
        "UPDATE document_public_copies SET title='rewritten'",
        "DELETE FROM document_public_copies",
    ]:
        with pytest.raises(DBAPIError, match="append-only"):
            async with postgres_sessions.begin() as db:
                await db.execute(text(sql))


async def test_staff_revocation_during_integrity_check_blocks_publication(
    postgres_sessions,
    court_document,
    monkeypatch,
):
    client, did, clerk, _, copy = court_document
    started, release = threading.Event(), threading.Event()
    hash_file = document_service.stored_integrity

    def pause_after_read(file_key):
        result = hash_file(file_key)
        started.set()
        assert release.wait(5), "Integrity check was not released"
        return result

    monkeypatch.setattr(document_service, "stored_integrity", pause_after_read)
    pending = asyncio.create_task(
        client.post(
            f"/api/v1/clerk/documents/{did}/publication",
            json={
                "copy_id": copy["id"],
                "reviewed": True,
                "expected_version": 0,
                "reason": "Authority revoked while this request was pending",
            },
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 5)
        async with postgres_sessions.begin() as db:
            await db.scalar(select(User).where(User.id == clerk).with_for_update())
            await db.execute(delete(UserCourtRole).where(UserCourtRole.user_id == clerk))
        release.set()
        assert (await asyncio.wait_for(pending, 5)).status_code == 403
        async with postgres_sessions() as db:
            doc = await db.get(FilingDocument, did)
            assert doc.public_copy_id is None and doc.access_version == 0
            assert not doc.is_confidential
    finally:
        release.set()
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
