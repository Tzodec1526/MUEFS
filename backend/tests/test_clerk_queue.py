from datetime import UTC, datetime, timedelta

import pytest_asyncio

from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.user import CourtRole, UserCourtRole
from tests.test_motions_and_search import create_court_with_case


@pytest_asyncio.fixture
async def queue_data(db_session, api_client):
    user, clerk, court, case_type, _, case = await create_court_with_case(db_session)
    db_session.add(UserCourtRole(user_id=clerk.id, court_id=court.id, role=CourtRole.CLERK))
    case.case_number = "MI-QUEUE-2026"
    old = datetime.now(UTC) - timedelta(hours=72)
    filings = [FilingEnvelope(
        court_id=court.id, case_type_id=case_type.id, filer_id=user.id,
        case_id=case.id if i == 0 else None,
        case_title="Claim 100%_ literal" if i == 1 else f"Claim {i}",
        status=FilingStatus.UNDER_REVIEW if i % 2 else FilingStatus.SUBMITTED,
        submitted_at=old if i < 28 else old + timedelta(hours=50),
    ) for i in range(31)]
    filings[2].case_title = "Claim 100AB wildcard"
    db_session.add_all(filings)
    waiver = FilingEnvelope(
        court_id=court.id, case_type_id=case_type.id, filer_id=user.id,
        case_title="Waiver still awaiting a decision", status=FilingStatus.ACCEPTED,
        submitted_at=old - timedelta(days=1), fee_waiver_requested=True,
        fee_waiver_reason="Private financial application",
    )
    db_session.add(waiver)
    other = Court(name="Other court", county="Wayne", court_type=CourtType.CIRCUIT)
    db_session.add(other)
    await db_session.flush()
    other_type = CaseType(court_id=other.id, code="CIV", name="Civil", category=CaseCategory.CIVIL)
    db_session.add(other_type)
    await db_session.flush()
    db_session.add(FilingEnvelope(
        court_id=other.id, case_type_id=other_type.id, filer_id=user.id,
        case_title="Claim 100%_ literal", status=FilingStatus.SUBMITTED, submitted_at=old,
    ))
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(clerk.id)
    return court, other, filings, waiver, old


async def test_queue_search_finds_a_reference_without_crossing_courts(api_client, queue_data):
    court, other, filings, _, _ = queue_data
    for search, expected in [
        (f"#{filings[-1].id}", [filings[-1].id]),
        ("mi-queue-2026", [filings[0].id]),
        ("100%_", [filings[1].id]),
        ("#999999999999999999999999999999999", []),
        ("no matching title", []),
    ]:
        response = await api_client.get("/api/v1/clerk/queue", params={
            "court_id": court.id, "search": search,
        })
        assert response.status_code == 200, response.text
        assert [f["id"] for f in response.json()["filings"]] == expected
        assert response.json()["total"] == len(expected)
    denied = await api_client.get("/api/v1/clerk/queue", params={
        "court_id": other.id, "search": "100%_",
    })
    assert denied.status_code == 403


async def test_queue_age_totals_cover_all_matching_pages(api_client, queue_data):
    court, _, filings, _, old = queue_data
    for page in (1, 2, 6):
        response = await api_client.get("/api/v1/clerk/queue", params={
            "court_id": court.id, "page_size": 5, "page": page,
        })
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total"] == 31
        assert [f["id"] for f in data["filings"]] == [
            f.id for f in filings[(page - 1) * 5:page * 5]
        ]
        assert data["waiting_48h"] == 28
        assert data["submitted_count"] == 16
        assert data["under_review_count"] == 15
        assert datetime.fromisoformat(data["oldest_submitted_at"]).replace(tzinfo=UTC) == old
        assert datetime.fromisoformat(data["as_of"]).tzinfo is not None
    aged = await api_client.get("/api/v1/clerk/queue", params={
        "court_id": court.id, "waiting_48h_only": True, "status": "under_review",
    })
    assert aged.status_code == 200, aged.text
    assert aged.json()["total"] == aged.json()["waiting_48h"] == 14
    assert all(f["status"] == "under_review" for f in aged.json()["filings"])


async def test_waiver_queue_search_keeps_accepted_pending_applications(api_client, queue_data):
    court, _, _, waiver, _ = queue_data
    response = await api_client.get("/api/v1/clerk/queue", params={
        "court_id": court.id, "fee_waivers": True, "search": f"#{waiver.id}",
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == data["waiting_48h"] == 1
    assert data["filings"][0]["status"] == "accepted"
    assert "Private financial application" not in response.text
