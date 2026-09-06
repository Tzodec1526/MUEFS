"""Recheck filing authority after authentication and order competing batch locks."""

import asyncio
import threading

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api import auth
from app.database import get_db
from app.main import app
from app.models.filing import FilingEnvelope
from app.models.filing_transaction import FilingTransaction
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import document_service, filing_service
from tests.test_filing_concurrency import POSTGRES_URL, prepare_filing
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest.mark.parametrize("action", ["submit", "accept"])
async def test_deactivation_after_authentication_blocks_filing_transition(
    postgres_sessions, action
):
    fid, filer, clerk = await prepare_filing(postgres_sessions)
    if action == "accept":
        async with postgres_sessions.begin() as db:
            await filing_service.submit_filing(db, fid)
    actor = filer if action == "submit" else clerk
    authenticated, revoked = asyncio.Event(), asyncio.Event()

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    async def authenticated_id():
        authenticated.set()
        await asyncio.wait_for(revoked.wait(), 5)
        return actor

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[auth.get_current_user_id] = authenticated_id
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            pending = asyncio.create_task(
                client.post(
                    f"/api/v1/filings/{fid}/submit"
                    if action == "submit"
                    else f"/api/v1/clerk/filings/{fid}/review",
                    **({"json": {"action": "accept"}} if action == "accept" else {}),
                )
            )
            try:
                await asyncio.wait_for(authenticated.wait(), 5)
                async with postgres_sessions.begin() as db:
                    user = await db.scalar(select(User).where(User.id == actor).with_for_update())
                    user.is_active = False
                revoked.set()
                response = await asyncio.wait_for(pending, 5)
                assert response.status_code == 403
            finally:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        async with postgres_sessions() as db:
            assert await db.scalar(select(func.count()).select_from(FilingTransaction)) == (
                0 if action == "submit" else 1
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(auth.get_current_user_id, None)


async def test_competing_reverse_order_batches_finish_without_duplicate_acceptance(
    postgres_sessions,
    stored_document,
):
    first, filer, clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        source = await db.get(FilingEnvelope, first)
        second = FilingEnvelope(
            court_id=source.court_id,
            case_type_id=source.case_type_id,
        filer_id=filer,
        case_title="Second filing",
        filing_type="initial",
        )
        other_clerk = User(
            email="batch-clerk@test.com",
            first_name="Other",
            last_name="Clerk",
            user_type=UserType.CLERK,
        )
        db.add_all([second, other_clerk])
        await db.flush()
        db.add(stored_document(second.id))
        db.add(
            UserCourtRole(user_id=other_clerk.id, court_id=source.court_id, role=CourtRole.CLERK)
        )
        await db.flush()
        await filing_service.submit_filing(db, first)
        await filing_service.submit_filing(db, second.id)
        second_id, other_id = second.id, other_clerk.id

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            results = await asyncio.wait_for(
                asyncio.gather(
                    client.post(
                        "/api/v1/clerk/queue/batch-review",
                        headers={"X-Demo-User-Id": str(clerk)},
                        json={"action": "accept", "filing_ids": [first, second_id]},
                    ),
                    client.post(
                        "/api/v1/clerk/queue/batch-review",
                        headers={"X-Demo-User-Id": str(other_id)},
                        json={"action": "accept", "filing_ids": [second_id, first]},
                    ),
                ),
                10,
            )
            assert all(result.status_code == 200 for result in results)
            assert sorted(fid for result in results for fid in result.json()["succeeded"]) == [
                first,
                second_id,
            ]
        async with postgres_sessions() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FilingTransaction)
                    .where(FilingTransaction.event_type == "accepted")
                )
                == 2
            )
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_slow_submission_does_not_block_same_filers_other_upload(
    postgres_sessions, monkeypatch,
):
    first, filer, _clerk = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        source = await db.get(FilingEnvelope, first)
        second = FilingEnvelope(
            court_id=source.court_id,
            case_type_id=source.case_type_id,
            filer_id=filer,
            case_title="Independent draft",
            filing_type="initial",
        )
        db.add(second)
        await db.flush()
        second_id = second.id

    started, release = threading.Event(), threading.Event()
    original_integrity = document_service.stored_integrity

    def slow_integrity(file_key):
        started.set()
        assert release.wait(10), "Test did not release the storage read"
        return original_integrity(file_key)

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    monkeypatch.setattr(document_service, "stored_integrity", slow_integrity)
    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(
            transport=ASGITransport(app), base_url="http://test",
            headers={"X-Demo-User-Id": str(filer)},
        ) as client:
            pending = asyncio.create_task(client.post(f"/api/v1/filings/{first}/submit"))
            try:
                assert await asyncio.to_thread(started.wait, 5)
                # The audit insert references this user. An exclusive user lock
                # would block its FK check until the unrelated submission ends.
                uploaded = await asyncio.wait_for(client.post(
                    f"/api/v1/filings/{second_id}/documents",
                    data={"title": "Complaint", "document_type_code": "COMPLAINT"},
                    files={"file": ("complaint.txt", b"Synthetic complaint", "text/plain")},
                ), 5)
                assert uploaded.status_code == 200
                assert not pending.done()
            finally:
                release.set()
                submitted = await pending
            assert submitted.status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)
