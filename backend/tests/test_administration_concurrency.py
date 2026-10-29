"""Administrative changes must remain safe with independent PostgreSQL connections."""

import asyncio

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api import auth
from app.config import settings
from app.database import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.court import Court, CourtType
from app.models.user import User, UserCourtRole, UserType
from tests.test_administration import account_payload
from tests.test_filing_concurrency import POSTGRES_URL
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MUEFS_TEST_POSTGRES_URL not configured")


@pytest.mark.parametrize("postgres_sessions", [False, True], indirect=True)
@pytest.mark.parametrize("operation", ["disable", "roles"])
@pytest.mark.parametrize("already_verified", [False, True])
async def test_concurrent_administration_cannot_remove_every_admin_or_lose_a_role_change(
    postgres_sessions,
    operation,
    already_verified,
    monkeypatch,
):
    async with postgres_sessions.begin() as db:
        users = [
            User(
                email=f"concurrent-admin-{i}@example.com",
                verified_email=f"concurrent-admin-{i}@example.com" if already_verified else None,
                first_name="Concurrent",
                last_name=str(i),
                user_type=kind,
                keycloak_id=f"subject-{i}",
            )
            for i, kind in enumerate([UserType.ADMIN, UserType.ADMIN, UserType.CLERK])
        ]
        court = Court(name="Administration Court", county="Wayne", court_type=CourtType.CIRCUIT)
        db.add_all([*users, court])

    async def decode(token):
        actor = next(user for user in users if user.keycloak_id == token)
        return {"sub": actor.keycloak_id, "email": actor.email, "email_verified": True}

    monkeypatch.setattr(auth, "decode_keycloak_access_token", decode)
    monkeypatch.setattr(settings, "allow_demo_mode", False)

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    authenticated = asyncio.Event()
    arrivals = 0

    async def concurrent_actor(
        db=Depends(get_db, scope="function"), user_id=Depends(auth.get_current_user_id),
    ):
        nonlocal arrivals
        # The function scope shares the session that authenticated this request, as
        # production does. Flushing its verified-email update makes each request hold its
        # own account row before either continues, so the overlap is not left to timing.
        actor = await auth.get_current_user(db, user_id)
        await db.flush()
        arrivals += 1
        if arrivals == 2:
            authenticated.set()
        await asyncio.wait_for(authenticated.wait(), 5)
        return actor

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[auth.get_current_user] = concurrent_actor
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            if operation == "disable":
                actions = [
                    client.put(
                        f"/api/v1/admin/users/{target.id}",
                        headers={"Authorization": f"Bearer {actor.keycloak_id}"},
                        json=account_payload(target, is_active=False),
                    )
                    for actor, target in [(users[0], users[1]), (users[1], users[0])]
                ]
            else:
                actions = [
                    client.post(
                        f"/api/v1/admin/courts/{court.id}/users/{users[2].id}/roles",
                        headers={"Authorization": f"Bearer {users[i].keycloak_id}"},
                        json={
                            "role": role,
                            "action": "grant",
                            "expected_version": 0,
                            "reason": "Concurrent staffing update",
                        },
                    )
                    for i, role in enumerate(["clerk", "admin"])
                ]
            responses = await asyncio.wait_for(asyncio.gather(*actions), 15)
        assert sorted(response.status_code for response in responses) == (
            [200, 403] if operation == "disable" and already_verified else [200, 409]
        )
        async with postgres_sessions() as db:
            if operation == "disable":
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(User)
                        .where(
                            User.user_type == UserType.ADMIN,
                            User.is_active.is_(True),
                        )
                    )
                    == 1
                )
            else:
                assert await db.scalar(select(func.count()).select_from(UserCourtRole)) == 1
                assert (await db.get(User, users[2].id)).administration_version == 1
            assert await db.scalar(select(func.count()).select_from(AuditLog)) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(auth.get_current_user, None)
