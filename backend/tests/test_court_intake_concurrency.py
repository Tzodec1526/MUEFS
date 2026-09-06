"""Real transactions protect intake publications, authority, and received filings."""

import asyncio
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, text

from app import database
from app.database import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.court import CaseType, Court
from app.models.filing import FilingEnvelope
from app.models.filing_transaction import FilingTransaction
from app.models.user import CourtRole, User, UserCourtRole
from app.services import filing_service
from tests.filing_requests import submission_review
from tests.test_filing_concurrency import POSTGRES_URL, prepare_filing
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest.mark.parametrize("postgres_sessions", ["e95b20d7a6f1"], indirect=True)
async def test_intake_migration_preserves_existing_flags_and_retained_publications(
    postgres_sessions, monkeypatch,
):
    from alembic.config import Config

    from alembic import command

    fid, _filer, administrator = await prepare_filing(postgres_sessions)

    def migrate(connection, operation, revision):
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.set_main_option(
            "script_location", str(Path(__file__).resolve().parents[1] / "alembic"),
        )
        config.attributes["connection"] = connection
        getattr(command, operation)(config, revision)

    async with postgres_sessions.begin() as db:
        filing = await db.get(FilingEnvelope, fid)
        court_id, case_type_id = filing.court_id, filing.case_type_id
        await db.execute(text("UPDATE courts SET is_efiling_enabled = false WHERE id = :id"),
                         {"id": court_id})
        await db.execute(text("UPDATE case_types SET is_active = false WHERE id = :id"),
                         {"id": case_type_id})
    for operation, revision in [
        ("upgrade", "head"), ("downgrade", "e95b20d7a6f1"), ("upgrade", "head"),
    ]:
        async with postgres_sessions.kw["bind"].connect() as connection:
            await connection.run_sync(migrate, operation, revision)
    async with postgres_sessions.begin() as db:
        court = await db.get(Court, court_id)
        assert not court.is_efiling_enabled and court.intake_version == 0
        assert court.intake_notice is None
        assert not (await db.get(CaseType, case_type_id)).is_active
        db.add(UserCourtRole(user_id=administrator, court_id=court_id, role=CourtRole.ADMIN))
    monkeypatch.setattr(database, "async_session", postgres_sessions)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test",
                           headers={"X-Demo-User-Id": str(administrator)}) as client:
        response = await client.put(f"/api/v1/courts/{court_id}/intake", json={
            "expected_version": 0, "is_efiling_enabled": True, "public_notice": None,
            "case_types": [{"id": case_type_id, "is_active": True}],
            "reason": "Synthetic reopening", "authority_reference": "Synthetic ADM-3",
        })
        assert response.status_code == 200, response.text
    with pytest.raises(RuntimeError, match="Cannot discard retained intake publications"):
        async with postgres_sessions.kw["bind"].connect() as connection:
            await connection.run_sync(migrate, "downgrade", "e95b20d7a6f1")
    async with postgres_sessions() as db:
        court = await db.get(Court, court_id)
        assert court.is_efiling_enabled and court.intake_version == 1
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "court_intake_changed", AuditLog.entity_id == court_id,
        )) == 1


@pytest_asyncio.fixture
async def intake_case(postgres_sessions, monkeypatch):
    fid, filer, administrator = await prepare_filing(postgres_sessions)
    async with postgres_sessions.begin() as db:
        filing = await db.get(FilingEnvelope, fid)
        court_id = filing.court_id
        types = list(await db.scalars(select(CaseType).where(CaseType.court_id == court_id)))
        db.add(UserCourtRole(user_id=administrator, court_id=court_id, role=CourtRole.ADMIN))
    monkeypatch.setattr(database, "async_session", postgres_sessions)
    body = {
        "expected_version": 0, "is_efiling_enabled": False,
        "public_notice": "Synthetic notice: contact the court for filing arrangements.",
        "case_types": [{"id": item.id, "is_active": True} for item in types],
        "reason": "Synthetic operations change", "authority_reference": "Synthetic ADM-2",
    }
    return fid, filer, administrator, court_id, body


@pytest.mark.parametrize("postgres_sessions", [True], indirect=True)
async def test_received_filings_remain_reviewable_and_receipts_survive_closure(
    intake_case, postgres_sessions,
):
    fid, filer, administrator, court_id, body = intake_case
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test",
                           headers={"X-Demo-User-Id": str(filer)}) as client:
        key = {"Idempotency-Key": str(uuid4())}
        review = await submission_review(client, fid)
        received = await client.post(f"/api/v1/filings/{fid}/submit", json=review, headers=key)
        assert received.status_code == 200, received.text
        async with postgres_sessions() as db:
            original = (await db.scalars(select(FilingTransaction))).one()
            receipt_id, receipt_details = original.id, original.details
        closed = await client.put(f"/api/v1/courts/{court_id}/intake", json=body,
                                  headers={"X-Demo-User-Id": str(administrator)})
        assert closed.status_code == 200, closed.text
        async with postgres_sessions() as db:
            assert (await db.get(Court, court_id)).intake_version == 1
            assert await db.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "court_intake_changed",
            )) == 1
        accepted = await client.post(f"/api/v1/clerk/filings/{fid}/review",
            headers={"X-Demo-User-Id": str(administrator)},
            json={"action": "accept", "expected_submission_count": 1})
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["status"] == "accepted"
        replay = await client.post(f"/api/v1/filings/{fid}/submit", json=review, headers=key)
        assert replay.status_code == 200 and replay.json()["submission_count"] == 1
    async with postgres_sessions() as db:
        assert (await db.get(FilingTransaction, receipt_id)).details == receipt_details


async def test_competing_publications_preserve_one_complete_winning_state(
    intake_case, postgres_sessions,
):
    _fid, _filer, administrator, court_id, first = intake_case
    second = deepcopy(first)
    second["is_efiling_enabled"] = True
    second["case_types"][0]["is_active"] = False
    second["public_notice"] = "Different synthetic instructions"
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test",
                           headers={"X-Demo-User-Id": str(administrator)}) as client:
        responses = await asyncio.gather(*(
            client.put(f"/api/v1/courts/{court_id}/intake", json=body) for body in [first, second]
        ))
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response.json() for response in responses if response.status_code == 200)
    async with postgres_sessions() as db:
        court = await db.get(Court, court_id)
        assert court.intake_version == 1
        assert court.is_efiling_enabled == winner["is_efiling_enabled"]
        assert court.intake_notice == winner["public_notice"]
        for item in winner["case_types"]:
            assert (await db.get(CaseType, item["id"])).is_active == item["is_active"]
        entries = (await db.scalars(select(AuditLog).where(
            AuditLog.action == "court_intake_changed",
        ))).all()
        assert len(entries) == 1 and entries[0].details["after"]["version"] == 1


async def test_failed_commit_restores_all_intake_settings(intake_case, postgres_sessions):
    _fid, _filer, administrator, court_id, body = intake_case
    body["case_types"][0]["is_active"] = False
    async with postgres_sessions.begin() as db:
        await db.execute(text("""
            CREATE FUNCTION reject_intake_publication() RETURNS trigger AS $$
            BEGIN
                IF NEW.action = 'court_intake_changed' THEN
                    RAISE EXCEPTION 'Synthetic deferred intake failure';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        await db.execute(text("""
            CREATE CONSTRAINT TRIGGER reject_intake_publication AFTER INSERT ON audit_log
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            EXECUTE FUNCTION reject_intake_publication();
        """))
    async with AsyncClient(transport=ASGITransport(app, raise_app_exceptions=False),
                           base_url="http://test") as client:
        response = await client.put(f"/api/v1/courts/{court_id}/intake", json=body,
                                    headers={"X-Demo-User-Id": str(administrator)})
    assert response.status_code == 500
    async with postgres_sessions() as db:
        court = await db.get(Court, court_id)
        assert court.intake_version == 0 and court.is_efiling_enabled
        assert court.intake_notice is None
        assert (await db.get(CaseType, body["case_types"][0]["id"])).is_active
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "court_intake_changed",
        )) == 0


@pytest.mark.parametrize("revocation", ["account", "assignment"])
async def test_publication_rechecks_authority_after_waiting_for_revocation(
    intake_case, postgres_sessions, revocation,
):
    _fid, _filer, administrator, court_id, body = intake_case
    pending = None
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        try:
            async with postgres_sessions.begin() as operator:
                actor = await operator.scalar(select(User).where(User.id == administrator)
                                               .with_for_update())
                blocker = await operator.scalar(text("SELECT pg_backend_pid()"))
                if revocation == "account":
                    actor.is_active = False
                else:
                    await operator.execute(delete(UserCourtRole).where(
                        UserCourtRole.user_id == administrator, UserCourtRole.court_id == court_id,
                        UserCourtRole.role == CourtRole.ADMIN,
                    ))
                await operator.flush()
                pending = asyncio.create_task(client.put(f"/api/v1/courts/{court_id}/intake",
                    json=body, headers={"X-Demo-User-Id": str(administrator)}))
                async with asyncio.timeout(5), postgres_sessions() as observer:
                    while not await observer.scalar(text("""
                        SELECT EXISTS (SELECT 1 FROM pg_stat_activity
                        WHERE :blocker = ANY(pg_blocking_pids(pid)))
                    """), {"blocker": blocker}):
                        await asyncio.sleep(0.01)
            response = await asyncio.wait_for(pending, timeout=5)
            assert response.status_code == 403, response.text
        finally:
            if pending is not None and not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
    async with postgres_sessions() as db:
        assert (await db.get(Court, court_id)).intake_version == 0


async def test_administrator_closure_waits_for_a_submission_receipt_to_commit(
    intake_case, postgres_sessions, monkeypatch,
):
    fid, filer, administrator, court_id, body = intake_case
    reached_storage, release, changing = asyncio.Event(), asyncio.Event(), asyncio.Event()
    verify = filing_service.verify_filing_documents

    async def pause_after_intake(filing):
        await verify(filing)
        reached_storage.set()
        await release.wait()

    monkeypatch.setattr(filing_service, "verify_filing_documents", pause_after_intake)
    closure_pid = None

    async def sessions(request: Request):
        nonlocal closure_pid
        async with postgres_sessions.begin() as db:
            if request.method == "PUT":
                closure_pid = await db.scalar(text("SELECT pg_backend_pid()"))
                changing.set()
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, sessions)
    pending = []
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test",
                               headers={"X-Demo-User-Id": str(filer)}) as client:
            review = await submission_review(client, fid)
            submission = asyncio.create_task(client.post(f"/api/v1/filings/{fid}/submit",
                json=review, headers={"Idempotency-Key": str(uuid4())}))
            pending.append(submission)
            await asyncio.wait_for(reached_storage.wait(), timeout=5)
            closure = asyncio.create_task(client.put(f"/api/v1/courts/{court_id}/intake",
                json=body, headers={"X-Demo-User-Id": str(administrator)}))
            pending.append(closure)
            await asyncio.wait_for(changing.wait(), timeout=5)
            async with asyncio.timeout(5), postgres_sessions() as observer:
                while await observer.scalar(text(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid",
                ), {"pid": closure_pid}) != "Lock":
                    await asyncio.sleep(0.01)
            assert not closure.done()
            release.set()
            assert (await asyncio.wait_for(submission, timeout=5)).status_code == 200
            assert (await asyncio.wait_for(closure, timeout=5)).status_code == 200
    finally:
        release.set()
        await asyncio.gather(*pending, return_exceptions=True)
    async with postgres_sessions() as db:
        assert (await db.get(FilingEnvelope, fid)).submission_count == 1
        assert not (await db.get(Court, court_id)).is_efiling_enabled
