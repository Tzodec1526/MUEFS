"""Participant updates serialize on PostgreSQL and recheck revoked staff authority."""

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.api import auth
from app.database import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.case import Case, CaseParticipant
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.user import CourtRole, User, UserCourtRole, UserType
from tests.test_filing_concurrency import POSTGRES_URL
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest.fixture
async def court_editors(postgres_sessions):
    async with postgres_sessions.begin() as db:
        users = [
            User(
                email=f"editor{i}@example.com",
                first_name="Editor",
                last_name=str(i),
                user_type=UserType.CLERK,
            )
            for i in range(2)
        ]
        counsel = User(
            email="counsel@example.com",
            first_name="Counsel",
            last_name="User",
            user_type=UserType.ATTORNEY,
            bar_number="P12345",
            bar_number_verified=True,
        )
        court = Court(name="Concurrent Court", county="Wayne", court_type=CourtType.CIRCUIT)
        db.add_all([*users, counsel, court])
        await db.flush()
        db.add_all(
            [
                UserCourtRole(user_id=user.id, court_id=court.id, role=CourtRole.CLERK)
                for user in users
            ]
        )
        case_type = CaseType(court_id=court.id, code="C", name="Civil", category=CaseCategory.CIVIL)
        db.add(case_type)
        await db.flush()
        case = Case(
            court_id=court.id,
            case_type_id=case_type.id,
            case_number="EDIT-1",
            title="Concurrent case",
            is_sealed=True,
            filed_date=datetime.now(UTC),
        )
        db.add(case)
    return users, counsel, case


@pytest.mark.parametrize("postgres_sessions", [False, True], indirect=True)
async def test_two_editors_cannot_overwrite_participants(postgres_sessions, court_editors):
    users, counsel, case = court_editors

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            responses = await asyncio.wait_for(
                asyncio.gather(
                    *[
                        client.post(
                            f"/api/v1/cases/{case.id}/participants",
                            json={
                                "party_name": "Counsel",
                                "role": "attorney",
                                "account_email": counsel.email,
                                "attorney_bar_number": counsel.bar_number,
                                "access_enabled": True,
                                "expected_version": 0,
                                "reason": "Court-reviewed appearance",
                            },
                            headers={"X-Demo-User-Id": str(actor.id)},
                        )
                        for actor in users
                    ]
                ),
                15,
            )
        assert sorted(response.status_code for response in responses) == [201, 409]
        async with postgres_sessions() as db:
            assert await db.scalar(select(func.count()).select_from(CaseParticipant)) == 1
            assert await db.scalar(select(func.count()).select_from(AuditLog)) == 1
            assert (await db.get(Case, case.id)).participant_version == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_revocation_after_authentication_prevents_pending_case_edit(
    postgres_sessions,
    court_editors,
):
    users, _, case = court_editors
    authenticated, revoked = asyncio.Event(), asyncio.Event()

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    async def pause_after_auth(db=Depends(get_db), user_id=Depends(auth.get_current_user_id)):
        actor = await auth.get_current_user(db, user_id)
        authenticated.set()
        await asyncio.wait_for(revoked.wait(), 5)
        return actor

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[auth.get_current_user] = pause_after_auth
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            pending = asyncio.create_task(
                client.post(
                    f"/api/v1/cases/{case.id}/participants",
                    json={
                        "party_name": "Party",
                        "role": "defendant",
                        "expected_version": 0,
                        "reason": "Pending before revocation",
                    },
                    headers={"X-Demo-User-Id": str(users[0].id)},
                )
            )
            try:
                await asyncio.wait_for(authenticated.wait(), 5)
                async with postgres_sessions.begin() as db:
                    # Administration changes lock this same account before retiring its role.
                    await db.scalar(select(User).where(User.id == users[0].id).with_for_update())
                    await db.execute(
                        delete(UserCourtRole).where(UserCourtRole.user_id == users[0].id)
                    )
                revoked.set()
                assert (await asyncio.wait_for(pending, 5)).status_code == 403
            finally:
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
        async with postgres_sessions() as db:
            assert await db.scalar(select(func.count()).select_from(CaseParticipant)) == 0
            assert await db.scalar(select(func.count()).select_from(AuditLog)) == 0
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(auth.get_current_user, None)
