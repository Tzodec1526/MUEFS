import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.database import get_db
from app.main import app
from app.models.notification import DeliveryStatus, Notification, NotificationDeliveryEvent
from app.models.service_delivery import ServiceEvent, ServiceRecipient
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.schemas.service_delivery import ServicePacketCreate
from app.services import email_delivery_service as email
from app.services.service_delivery_service import create_packet
from tests.test_email_delivery import smtp_sink as smtp_sink
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions
from tests.test_service_deliveries import (
    delivery_case as delivery_case,
)
from tests.test_service_deliveries import (
    prepare_delivery,
    send,
)


@pytest.fixture
async def failure_case(delivery_case, db_session, api_client):
    f = delivery_case
    assert (await send(api_client, f)).status_code == 201
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    while await email.deliver_next(sessions):
        pass
    recipient = await db_session.scalar(select(ServiceRecipient))
    notice = await db_session.get(Notification, recipient.notification_id)
    api_client.headers["X-Demo-User-Id"] = str(f["staff"])
    return (
        f,
        recipient,
        notice,
        {
            "source": "relay_notice",
            "source_reference": "Synthetic relay ticket 42",
            "description": "The relay reports that the destination mailbox rejected the message.",
            "observed_at": datetime.now(UTC).isoformat(),
            "expected_message_id": notice.email_message_id,
            "expected_attempt_count": notice.attempt_count,
            "reviewed": True,
        },
    )


async def test_failure_report_retains_evidence_and_alerts_sender_once(
    failure_case, db_session, api_client
):
    f, recipient, notice, data = failure_case
    path = f"/api/v1/service/deliveries/{recipient.id}"
    old_message, sent_at = notice.email_message, notice.sent_at
    assert notice.delivery_status == DeliveryStatus.SENT and sent_at
    data["observed_at"] = notice.last_attempt_at.replace(tzinfo=UTC, microsecond=0).isoformat()
    assert (await api_client.get(path)).json()["can_report_failure"]
    headers = {"Idempotency-Key": str(uuid4())}
    first = await api_client.post(path + "/failure-reports", json=data, headers=headers)
    assert first.status_code == 201, first.text
    replay = await api_client.post(path + "/failure-reports", json=data, headers=headers)
    assert replay.json() == first.json()
    assert first.json()["delivery_status"] == "failure_reported"
    assert notice.sent_at == sent_at and notice.email_message == old_message
    assert notice.next_attempt_at is None
    reports = list(await db_session.scalars(select(ServiceEvent)))
    assert len(reports) == 1 and reports[0].details["previous_status"] == "sent"
    assert reports[0].details["source_reference"] == data["source_reference"]
    events = list(
        await db_session.scalars(
            select(NotificationDeliveryEvent.outcome)
            .where(
                NotificationDeliveryEvent.notification_id == notice.id,
            )
            .order_by(NotificationDeliveryEvent.id)
        )
    )
    assert events == ["queued", "started", "accepted"]
    alert = await db_session.get(Notification, reports[0].details["sender_notification_id"])
    assert alert.recipient_id == f["sender"] and alert.delivery_status == DeliveryStatus.PENDING
    assert "failure" in alert.body and recipient.id in alert.body
    assert "Synthetic relay ticket" not in alert.email_message
    changed = await api_client.post(
        path + "/failure-reports", json={**data, "description": "Different report"}, headers=headers
    )
    assert changed.status_code == 409
    api_client.headers["X-Demo-User-Id"] = str(f["sender"])
    assert not (await api_client.get(path)).json()["can_retry"]
    assert (await api_client.post(path + "/retry", json={"reason": "Try again"})).status_code == 403
    attention = (await api_client.get("/api/v1/notifications")).json()["notifications"]
    assert any(item["id"] == alert.id for item in attention)


@pytest.mark.parametrize(
    "change,expected",
    [
        ("sender", 403),
        ("recipient", 403),
        ("other_staff", 403),
        ("message", 409),
        ("attempt", 409),
        ("sending", 409),
        ("future", 422),
        ("before_send", 422),
        ("unreviewed", 422),
        ("blank_reference", 422),
    ],
)
async def test_invalid_or_stale_report_cannot_change_transport_state(
    failure_case,
    db_session,
    api_client,
    change,
    expected,
):
    f, recipient, notice, data = failure_case
    if change in ("sender", "recipient"):
        api_client.headers["X-Demo-User-Id"] = str(
            f["sender" if change == "sender" else "receiver"]
        )
    elif change == "other_staff":
        outsider = User(
            email="unassigned@example.com",
            first_name="Other",
            last_name="Clerk",
            user_type=UserType.CLERK,
        )
        db_session.add(outsider)
        await db_session.flush()
        api_client.headers["X-Demo-User-Id"] = str(outsider.id)
    elif change == "message":
        data["expected_message_id"] = "<different@example.com>"
    elif change == "attempt":
        data["expected_attempt_count"] += 1
    elif change == "sending":
        notice.delivery_status = DeliveryStatus.SENDING
    elif change == "future":
        data["observed_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    elif change == "before_send":
        data["observed_at"] = (
            notice.last_attempt_at.replace(tzinfo=UTC) - timedelta(seconds=1)
        ).isoformat()
    elif change == "unreviewed":
        data["reviewed"] = False
    elif change == "blank_reference":
        data["source_reference"] = "   "
    await db_session.flush()
    before_status = notice.delivery_status
    response = await api_client.post(
        f"/api/v1/service/deliveries/{recipient.id}/failure-reports",
        json=data,
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == expected, response.text
    assert notice.delivery_status == before_status
    assert await db_session.scalar(select(func.count()).select_from(ServiceEvent)) == 0


async def test_report_replay_does_not_replace_a_reviewed_retry(
    failure_case, db_session, api_client
):
    _, recipient, notice, data = failure_case
    path = f"/api/v1/service/deliveries/{recipient.id}"
    headers = {"Idempotency-Key": str(uuid4())}
    first = await api_client.post(path + "/failure-reports", json=data, headers=headers)
    assert first.status_code == 201
    retry = await api_client.post(
        path + "/retry",
        json={"reason": "Relay ticket reviewed; temporary mailbox rejection resolved"},
    )
    assert retry.status_code == 200 and notice.delivery_status == DeliveryStatus.PENDING
    assert notice.email_message_id != data["expected_message_id"]
    replay = await api_client.post(path + "/failure-reports", json=data, headers=headers)
    assert replay.status_code == 201 and replay.json()["report_id"] == first.json()["report_id"]
    assert replay.json()["delivery_status"] == "pending"
    stale = await api_client.post(
        path + "/failure-reports", json=data, headers={"Idempotency-Key": str(uuid4())}
    )
    assert stale.status_code == 409 and notice.delivery_status == DeliveryStatus.PENDING
    assert (await api_client.get(path + "/events")).json()["events"][0][
        "action"
    ] == "retry_requested"


async def test_failure_report_remains_visible_after_a_late_smtp_reply(
    failure_case, db_session, api_client
):
    _, recipient, notice, data = failure_case
    notice.delivery_status = DeliveryStatus.UNKNOWN
    await db_session.flush()
    detached_attempt = Notification(
        id=notice.id, attempt_count=notice.attempt_count, email_message_id=notice.email_message_id
    )
    response = await api_client.post(
        f"/api/v1/service/deliveries/{recipient.id}/failure-reports",
        json=data,
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    await email.finish_attempt(sessions, detached_attempt, "accepted", 250, None)
    await db_session.refresh(notice)
    assert notice.delivery_status == DeliveryStatus.FAILURE_REPORTED


@pytest.mark.skipif(
    not os.getenv("MUEFS_TEST_POSTGRES_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.parametrize("postgres_sessions", [False, True], indirect=True)
async def test_two_court_reviewers_cannot_duplicate_report_or_override_retry(
    postgres_sessions,
    smtp_sink,
    stored_document,
    monkeypatch,
):
    monkeypatch.setattr(settings, "service_delivery_enabled", True)
    async with postgres_sessions.begin() as db:
        f = await prepare_delivery(db, stored_document)
        packet = await create_packet(
            db, f["sender"], f["fid"], ServicePacketCreate(**f["data"]), str(uuid4())
        )
        recipient = await db.scalar(
            select(ServiceRecipient).where(ServiceRecipient.packet_id == packet.id)
        )
        other = User(
            email="reviewer2@example.com",
            first_name="Second",
            last_name="Reviewer",
            user_type=UserType.CLERK,
        )
        db.add(other)
        await db.flush()
        db.add(UserCourtRole(user_id=other.id, court_id=f["case"].court_id, role=CourtRole.CLERK))
    while await email.deliver_next(postgres_sessions):
        pass
    async with postgres_sessions() as db:
        notice = await db.get(Notification, recipient.notification_id)
        data = {
            "source": "recipient_report",
            "source_reference": "Synthetic case contact log",
            "description": "Recipient reported an undeliverable message",
            "reviewed": True,
            "observed_at": datetime.now(UTC).isoformat(),
            "expected_message_id": notice.email_message_id,
            "expected_attempt_count": notice.attempt_count,
        }

    async def database():
        async with postgres_sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            path = f"/api/v1/service/deliveries/{recipient.id}"
            key = str(uuid4())

            async def report(uid, report_key):
                return await client.post(
                    path + "/failure-reports",
                    json=data,
                    headers={"X-Demo-User-Id": str(uid), "Idempotency-Key": report_key},
                )

            first, second = await asyncio.wait_for(
                asyncio.gather(report(f["staff"], key), report(other.id, key)), 15
            )
            assert first.status_code == second.status_code == 201
            assert first.json()["report_id"] == second.json()["report_id"]
            report_result, retry_result = await asyncio.wait_for(
                asyncio.gather(
                    report(f["staff"], str(uuid4())),
                    client.post(
                        path + "/retry",
                        headers={"X-Demo-User-Id": str(other.id)},
                        json={"reason": "Source reviewed, mailbox restored"},
                    ),
                ),
                15,
            )
            assert report_result.status_code in (201, 409) and retry_result.status_code == 200
        async with postgres_sessions() as db:
            current = await db.get(Notification, recipient.notification_id)
            assert current.delivery_status == DeliveryStatus.PENDING
            assert current.email_message_id != data["expected_message_id"]
    finally:
        app.dependency_overrides.pop(get_db, None)
