import asyncio
import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.database import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.user import UserType
from app.services import filing_service
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions
from tests.test_motions_and_search import create_court_with_case


async def test_retry_returns_current_filing_without_repeating_creation(db_session, api_client):
    user, _clerk, court, case_type, _other_type, _case = await create_court_with_case(db_session)
    headers = {"X-Demo-User-Id": str(user.id), "Idempotency-Key": str(uuid4())}
    body = {"court_id": court.id, "case_type_id": case_type.id,
            "filing_type": "initial", "case_title": "Original draft"}
    first = await api_client.post("/api/v1/filings", json=body, headers=headers)
    assert first.status_code == 201, first.text
    retry = await api_client.post("/api/v1/filings", json=body, headers=headers)
    assert retry.status_code == 200, retry.text
    assert retry.json()["id"] == first.json()["id"]
    filing = await db_session.get(FilingEnvelope, first.json()["id"])
    filing.case_title = "Later saved details"
    filing.status = FilingStatus.SUBMITTED
    filing.submission_count = 1
    court.is_efiling_enabled = False
    await db_session.flush()

    replay = await api_client.post("/api/v1/filings", json={**body, "fee_waiver_requested": False},
                                   headers=headers)
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == filing.id
    assert replay.json()["case_title"] == "Later saved details"
    assert replay.json()["status"] == "submitted"
    assert await db_session.scalar(select(func.count()).select_from(FilingEnvelope)) == 1
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.action == "create_filing")) == 1

    changed = await api_client.post("/api/v1/filings", json={**body, "case_title": "Changed retry"},
                                    headers=headers)
    assert changed.status_code == 409, changed.text
    assert changed.json()["filing_id"] == filing.id
    assert filing.case_title == "Later saved details"
    user.is_active = False
    await db_session.flush()
    denied = await api_client.post("/api/v1/filings", json=body, headers=headers)
    assert denied.status_code == 401
    assert "filing_id" not in denied.json()
    user.is_active = True
    user.user_type = UserType.PUBLIC
    await db_session.flush()
    assert (await api_client.post("/api/v1/filings", json=body, headers=headers)).status_code == 403


@pytest.mark.parametrize("key", [None, "not-a-uuid"])
async def test_creation_requires_a_valid_retry_key(db_session, api_client, key):
    user, _clerk, court, case_type, *_ = await create_court_with_case(db_session)
    headers = {"X-Demo-User-Id": str(user.id)}
    if key is not None:
        headers["Idempotency-Key"] = key
    response = await api_client.post("/api/v1/filings", headers=headers, json={
        "court_id": court.id, "case_type_id": case_type.id, "filing_type": "initial",
    })
    assert response.status_code == 422, response.text
    assert await db_session.scalar(select(func.count()).select_from(FilingEnvelope)) == 0


@pytest.mark.skipif(not os.getenv("MUEFS_TEST_POSTGRES_URL"), reason="PostgreSQL not configured")
@pytest.mark.parametrize("postgres_sessions", [True], indirect=True)
@pytest.mark.parametrize("different_details", [False, True])
async def test_concurrent_creations_commit_once_and_keep_user_keys_separate(
    postgres_sessions, monkeypatch, different_details,
):
    async with postgres_sessions.begin() as db:
        user, other, court, case_type, *_ = await create_court_with_case(db)
        user_id, other_id = user.id, other.id
        body = {"court_id": court.id, "case_type_id": case_type.id,
                "filing_type": "initial", "case_title": "Concurrent creation"}

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    headers = {"X-Demo-User-Id": str(user_id), "Idempotency-Key": str(uuid4())}
    create = filing_service.create_filing
    reached = 0
    all_read = asyncio.Event()

    async def synchronized_create(db, filer_id, data, **kwargs):
        nonlocal reached
        if filer_id == user_id:
            reached += 1
            if reached == 4:
                all_read.set()
            await asyncio.wait_for(all_read.wait(), 5)
        return await create(db, filer_id, data, **kwargs)

    monkeypatch.setattr(filing_service, "create_filing", synchronized_create)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            responses = await asyncio.wait_for(asyncio.gather(*[
                client.post("/api/v1/filings", json={**body, "case_title":
                    "Different details" if different_details and i % 2 else body["case_title"]},
                    headers=headers) for i in range(4)
            ]), 15)
            expected = [200, 201, 409, 409] if different_details else [200, 200, 200, 201]
            assert sorted(r.status_code for r in responses) == expected
            ids = {r.json().get("id", r.json().get("filing_id")) for r in responses}
            assert len(ids) == 1
            original_id = ids.pop()
            separate = await client.post("/api/v1/filings", json=body, headers={
                **headers, "X-Demo-User-Id": str(other_id),
            })
            assert separate.status_code == 201, separate.text
            assert separate.json()["id"] != original_id
            async with postgres_sessions() as db:
                assert await db.scalar(select(func.count()).select_from(FilingEnvelope)) == 2
                assert await db.scalar(select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == "create_filing")) == 2
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.skipif(not os.getenv("MUEFS_TEST_POSTGRES_URL"), reason="PostgreSQL not configured")
async def test_retry_finds_winner_when_intake_closes_between_lookup_and_validation(
    postgres_sessions, monkeypatch,
):
    from app.models.court import Court

    async with postgres_sessions.begin() as db:
        user, _clerk, court, case_type, *_ = await create_court_with_case(db)
        user_id, court_id = user.id, court.id
        body = {"court_id": court.id, "case_type_id": case_type.id, "filing_type": "initial"}

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    reached, release = asyncio.Event(), asyncio.Event()
    create = filing_service.create_filing

    async def delayed_create(db, filer_id, data, **kwargs):
        if not reached.is_set():
            reached.set()
            await asyncio.wait_for(release.wait(), 10)
        return await create(db, filer_id, data, **kwargs)

    monkeypatch.setattr(filing_service, "create_filing", delayed_create)
    app.dependency_overrides[get_db] = database
    pending = None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                               headers={"X-Demo-User-Id": str(user_id),
                                        "Idempotency-Key": str(uuid4())}) as client:
            pending = asyncio.create_task(client.post("/api/v1/filings", json=body))
            await asyncio.wait_for(reached.wait(), 5)
            winner = await client.post("/api/v1/filings", json=body)
            assert winner.status_code == 201, winner.text
            async with postgres_sessions.begin() as db:
                court = await db.get(Court, court_id)
                court.is_efiling_enabled = False
            release.set()
            retry = await asyncio.wait_for(pending, 5)
            assert retry.status_code == 200, retry.text
            assert retry.json()["id"] == winner.json()["id"]
    finally:
        release.set()
        if pending is not None:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        app.dependency_overrides.pop(get_db, None)
