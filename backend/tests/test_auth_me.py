"""GET /auth/me includes court assignments for the SPA session."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.main import app
from app.models.court import Court, CourtType
from app.models.user import CourtRole, User, UserCourtRole, UserType


@pytest.mark.asyncio
async def test_auth_me_returns_court_assignments(db_session):
    clerk = User(
        email="me_clerk@test.com",
        first_name="C",
        last_name="Lerk",
        user_type=UserType.CLERK,
    )
    db_session.add(clerk)
    court = Court(name="Me Court", county="Ingham", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()
    db_session.add(UserCourtRole(
        user_id=clerk.id, court_id=court.id, role=CourtRole.CLERK,
    ))
    await db_session.commit()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Demo-User-Id": str(clerk.id)},
        ) as client:
            r = await client.get("/api/v1/auth/me")
            assert r.status_code == 200
            body = r.json()
            assert body["user_type"] == "clerk"
            assert body["court_assignments"][0]["court_id"] == court.id
            assert body["court_assignments"][0]["role"] == "clerk"
            assert body["court_assignments"][0]["court_name"] == "Me Court"
    finally:
        app.dependency_overrides.clear()
