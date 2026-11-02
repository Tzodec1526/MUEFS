import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, text

from app import database
from app.main import app
from app.models.audit import AuditLog
from app.models.case import Case, CaseParticipant
from app.models.user import User, UserCourtRole
from tests.test_case_participant_concurrency import court_editors as court_editors
from tests.test_filing_concurrency import POSTGRES_URL
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest.fixture
def public_instruction(postgres_sessions, monkeypatch):
    monkeypatch.setattr(database, "async_session", postgres_sessions)
    return {"expected_version": 0, "is_sealed": False, "confirm_public_release": True,
            "reason": "Synthetic public instruction", "authority_reference": "Synthetic ADM-10"}


@pytest.mark.parametrize("postgres_sessions", [True], indirect=True)
@pytest.mark.parametrize("competing_write", ["public_access", "participant"])
async def test_access_instructions_and_participant_edits_have_one_committed_winner(
    postgres_sessions, court_editors, public_instruction, competing_write,
):
    users, counsel, case = court_editors
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        path = f"/api/v1/cases/{case.id}"
        other = {"X-Demo-User-Id": str(users[1].id)}
        competing = (client.put(path + "/public-access", headers=other,
            json={**public_instruction, "authority_reference": "Synthetic ADM-11"})
            if competing_write == "public_access" else client.post(path + "/participants",
            headers=other, json={"party_name": "Counsel", "role": "attorney",
                "account_email": counsel.email, "attorney_bar_number": counsel.bar_number,
                "access_enabled": True, "expected_version": 0, "reason": "Synthetic appearance"}))
        first, second = await asyncio.wait_for(asyncio.gather(
            client.put(path + "/public-access", json=public_instruction,
                       headers={"X-Demo-User-Id": str(users[0].id)}), competing,
        ), timeout=10)
    assert sorted([first.status_code, second.status_code]) in ([200, 409], [201, 409])
    async with postgres_sessions() as db:
        current = await db.get(Case, case.id)
        assert current.participant_version == 1
        audit = (await db.scalars(select(AuditLog))).one()
        if audit.action == "case.public_access_changed":
            assert not current.is_sealed
            assert audit.details["before"]["is_sealed"] is True
            assert audit.details["after"]["participant_version"] == 1
            assert await db.scalar(select(func.count()).select_from(CaseParticipant)) == 0
        else:
            assert current.is_sealed and audit.action == "case.participant_created"
            assert await db.scalar(select(func.count()).select_from(CaseParticipant)) == 1


async def test_audit_commit_failure_rolls_back_public_access(
    postgres_sessions, court_editors, public_instruction,
):
    users, _counsel, case = court_editors
    async with postgres_sessions.begin() as db:
        await db.execute(text("""
            CREATE FUNCTION reject_case_access() RETURNS trigger AS $$
            BEGIN
                IF NEW.action = 'case.public_access_changed' THEN
                    RAISE EXCEPTION 'Synthetic deferred access failure';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        await db.execute(text("""
            CREATE CONSTRAINT TRIGGER reject_case_access AFTER INSERT ON audit_log
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_case_access();
        """))
    async with AsyncClient(transport=ASGITransport(app, raise_app_exceptions=False),
                           base_url="http://test") as client:
        response = await client.put(f"/api/v1/cases/{case.id}/public-access",
            json=public_instruction, headers={"X-Demo-User-Id": str(users[0].id)})
    assert response.status_code == 500
    async with postgres_sessions() as db:
        current = await db.get(Case, case.id)
        assert current.is_sealed and current.participant_version == 0
        assert await db.scalar(select(func.count()).select_from(AuditLog)) == 0


@pytest.mark.parametrize("revocation", ["account", "assignment"])
async def test_waiting_public_instruction_rechecks_revoked_authority(
    postgres_sessions, court_editors, public_instruction, revocation,
):
    users, _counsel, case = court_editors
    pending = None
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        try:
            async with postgres_sessions.begin() as operator:
                actor = await operator.scalar(select(User).where(User.id == users[0].id)
                                               .with_for_update())
                blocker = await operator.scalar(text("SELECT pg_backend_pid()"))
                if revocation == "account":
                    actor.is_active = False
                else:
                    await operator.execute(delete(UserCourtRole).where(
                        UserCourtRole.user_id == actor.id, UserCourtRole.court_id == case.court_id,
                    ))
                await operator.flush()
                pending = asyncio.create_task(client.put(
                    f"/api/v1/cases/{case.id}/public-access", json=public_instruction,
                    headers={"X-Demo-User-Id": str(actor.id)},
                ))
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
        current = await db.get(Case, case.id)
        assert current.is_sealed and current.participant_version == 0
