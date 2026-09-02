"""HTTP: a draft on a sealed case must not unlock the docket."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.main import app
from app.models.case import Case, CaseStatus
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.user import User, UserType


@pytest.mark.asyncio
async def test_stranger_draft_does_not_unlock_sealed_case(db_session):
    party = User(
        email="sealed_party_http@test.com",
        first_name="P",
        last_name="arty",
        user_type=UserType.SELF_REPRESENTED,
    )
    stranger = User(
        email="sealed_stranger_http@test.com",
        first_name="S",
        last_name="tranger",
        user_type=UserType.ATTORNEY,
        bar_number="P40404",
    )
    db_session.add_all([party, stranger])
    court = Court(name="IDOR Court", county="Wayne", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()
    ct = CaseType(
        court_id=court.id, code="CIV", name="Civil",
        category=CaseCategory.CIVIL, filing_fee_cents=15000,
    )
    db_session.add(ct)
    await db_session.flush()
    case = Case(
        court_id=court.id, case_number="MI-SEAL-IDOR-1", case_type_id=ct.id,
        title="Sealed v Hidden", status=CaseStatus.OPEN,
        filed_date=datetime.now(UTC), is_sealed=True,
    )
    db_session.add(case)
    await db_session.commit()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Demo-User-Id": str(stranger.id)},
        ) as client:
            created = await client.post(
                "/api/v1/filings",
                json={
                    "court_id": court.id,
                    "case_id": case.id,
                    "case_type_id": ct.id,
                    "case_title": "Should not attach",
                },
            )
            assert created.status_code == 403
            docket = await client.get(f"/api/v1/cases/{case.id}")
            assert docket.status_code == 403
    finally:
        app.dependency_overrides.clear()
