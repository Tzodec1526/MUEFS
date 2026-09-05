"""Notification history is scoped to the recipient and paginated stably."""

import pytest

from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingEnvelope
from app.models.notification import Notification, NotificationType
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import filing_service


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
async def test_clerk_accept_notifies_filer_in_both_review_paths(db_session, api_client, batch):
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
                            case_title="Notification test")
    db_session.add(filing)
    await db_session.flush()
    await filing_service.submit_filing(db_session, filing.id)
    api_client.headers["X-Demo-User-Id"] = str(clerk.id)
    if batch:
        response = await api_client.post("/api/v1/clerk/queue/batch-review", json={
            "action": "accept", "filing_ids": [filing.id],
        })
        assert response.json()["succeeded"] == [filing.id]
    else:
        response = await api_client.post(f"/api/v1/clerk/filings/{filing.id}/review", json={
            "action": "accept",
        })
    assert response.status_code == 200
    api_client.headers["X-Demo-User-Id"] = str(filer.id)
    notices = (await api_client.get("/api/v1/notifications")).json()
    assert notices["total"] == 2
    assert "accepted" in notices["notifications"][0]["subject"].lower()
