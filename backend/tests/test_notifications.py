from datetime import UTC, datetime

import pytest

from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingEnvelope
from app.models.notification import DeliveryStatus, Notification, NotificationType
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import filing_service
from tests.test_case_participants import participants_case as participants_case


@pytest.mark.parametrize("scope", ["mine", "court"])
async def test_filing_notice_lookup_preserves_scope_status_counts_and_stable_pages(
    participants_case, db_session, api_client, scope,
):
    users, cases = participants_case
    filings = [FilingEnvelope(court_id=case.court_id, case_id=case.id,
        case_type_id=case.case_type_id, filer_id=users[2].id) for case in [*cases, cases[0]]]
    db_session.add_all(filings)
    await db_session.flush()
    notices = [Notification(recipient_id=users[2].id, filing_envelope_id=filings[0].id,
        notification_type=NotificationType.CASE_UPDATE, subject=f"Target filing notice {i}",
        body="Retained update", created_at=datetime(2026, 1, 1, tzinfo=UTC),
        delivery_status=DeliveryStatus.FAILED if i % 2 == 0 else DeliveryStatus.PENDING)
        for i in range(29)]
    other_recipient = Notification(recipient_id=users[3].id, filing_envelope_id=filings[0].id,
        notification_type=NotificationType.CASE_UPDATE, subject="Other recipient", body="Private")
    db_session.add_all([*notices, other_recipient, *[
        Notification(recipient_id=users[2].id, filing_envelope_id=filing.id,
            notification_type=NotificationType.CASE_UPDATE,
            subject="Different filing", body="Other")
        for filing in filings[1:]
    ]])
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(users[0 if scope == "court" else 2].id)
    params = {"filing_id": filings[0].id, "page_size": 10}
    if scope == "court":
        params["court_id"] = cases[0].court_id
    first = (await api_client.get("/api/v1/notifications", params=params)).json()
    assert first["total"] == (30 if scope == "court" else 29)
    assert all(item["filing_envelope_id"] == filings[0].id for item in first["notifications"])
    if scope == "mine":
        assert "Other recipient" not in str(first)
    params.update(delivery_status="failed", page=2)
    second = (await api_client.get("/api/v1/notifications", params=params)).json()
    expected = [item.id for item in reversed(notices)
                if item.delivery_status == DeliveryStatus.FAILED]
    assert second["total"] == 15
    assert [item["id"] for item in second["notifications"]] == expected[10:]
    params.update(page=1, filing_id=filings[1].id)
    params.pop("delivery_status")
    foreign = (await api_client.get("/api/v1/notifications", params=params)).json()
    assert foreign["total"] == (0 if scope == "court" else 1)
    params["filing_id"] = 2_147_483_647
    assert (await api_client.get("/api/v1/notifications", params=params)).json()["total"] == 0
    params.update(filing_id=filings[0].id, court_id=cases[0].court_id)
    api_client.headers["X-Demo-User-Id"] = str(users[1].id)
    assert (await api_client.get("/api/v1/notifications", params=params)).status_code == 403


@pytest.mark.parametrize("filing_id", [0, -1, "1.5", "not-a-number", 2_147_483_648])
async def test_invalid_notice_filing_filter_is_rejected(participants_case, api_client, filing_id):
    response = await api_client.get("/api/v1/notifications", params={"filing_id": filing_id})
    assert response.status_code == 422


async def test_notification_history_recipient_and_paging(db_session, api_client):
    users = [
        User(email=f"notify{i}@test.com", first_name="Notify", last_name=str(i),
             user_type=UserType.ATTORNEY) for i in range(2)
    ]
    db_session.add_all(users)
    await db_session.flush()
    records = [
        Notification(recipient_id=users[0].id, notification_type=NotificationType.CASE_UPDATE,
                     subject=f"Update {i}", body="Body") for i in range(3)
    ]
    db_session.add_all([
        *records,
        Notification(recipient_id=users[1].id, notification_type=NotificationType.CASE_UPDATE,
                     subject="Private", body="Someone else's notice"),
    ])
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(users[0].id)
    listing = await api_client.get("/api/v1/notifications?page=2&page_size=2")
    assert listing.status_code == 200
    assert listing.json()["total"] == 3
    assert [n["id"] for n in listing.json()["notifications"]] == [records[0].id]
    assert "Someone else's notice" not in listing.text


@pytest.mark.parametrize("batch", [False, True])
async def test_clerk_accept_notifies_filer_in_both_review_paths(
    db_session, api_client, batch, stored_document,
):
    filer = User(email="filer@notify.test", first_name="F", last_name="Filer",
                 user_type=UserType.ATTORNEY)
    clerk = User(email="clerk@notify.test", first_name="C", last_name="Clerk",
                 user_type=UserType.CLERK)
    court = Court(name="Notification Court", county="Wayne", court_type=CourtType.CIRCUIT)
    db_session.add_all([filer, clerk, court])
    await db_session.flush()
    case_type = CaseType(court_id=court.id, code="CIV", name="Civil", category=CaseCategory.CIVIL)
    db_session.add(case_type)
    db_session.add(UserCourtRole(user_id=clerk.id, court_id=court.id, role=CourtRole.CLERK))
    await db_session.flush()
    filing = FilingEnvelope(court_id=court.id, case_type_id=case_type.id, filer_id=filer.id,
                            filing_type="initial", case_title="Notification test")
    db_session.add(filing)
    await db_session.flush()
    db_session.add(stored_document(filing.id))
    await db_session.flush()
    await filing_service.submit_filing(db_session, filing.id)
    api_client.headers["X-Demo-User-Id"] = str(clerk.id)
    if batch:
        response = await api_client.post(
            "/api/v1/clerk/queue/batch-review",
            json={
                "action": "accept",
                "filings": [{"filing_id": filing.id, "expected_submission_count": 1}],
            },
        )
        assert response.json()["succeeded"] == [filing.id]
    else:
        response = await api_client.post(
            f"/api/v1/clerk/filings/{filing.id}/review",
            json={
                "expected_submission_count": 1,
                "action": "accept",
            },
        )
    assert response.status_code == 200
    api_client.headers["X-Demo-User-Id"] = str(filer.id)
    notices = (await api_client.get("/api/v1/notifications")).json()
    assert notices["total"] == 2
    assert "accepted" in notices["notifications"][0]["subject"].lower()
