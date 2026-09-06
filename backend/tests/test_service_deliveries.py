"""Retained deliveries, scoped downloads, stale selections and real local SMTP."""

import asyncio
import json
import os
from datetime import UTC, datetime
from email import policy
from email.parser import Parser
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app import case_export
from app.config import settings
from app.models.case import Case, CaseParticipant, ParticipantRole
from app.models.filing import FilingEnvelope
from app.models.filing_transaction import FilingTransaction
from app.models.notification import DeliveryStatus, Notification, ServiceContact
from app.models.service_delivery import ServiceEvent, ServicePacket, ServiceRecipient
from app.models.user import User
from app.schemas.service_delivery import ServiceFailureReport, ServicePacketCreate
from app.services import document_service, email_delivery_service, filing_service
from app.services.case_participant_service import participant_snapshot
from app.services.service_delivery_service import create_packet
from tests.test_case_export import case_records as case_records
from tests.test_email_delivery import mail_sessions as mail_sessions
from tests.test_email_delivery import smtp_sink as smtp_sink
from tests.test_filing_concurrency import postgres_sessions as postgres_sessions
from tests.test_filing_history import filing_fixture


async def prepare_delivery(db, stored_document):
    fid, sender, staff, receiver = await filing_fixture(db)
    filing = await db.get(FilingEnvelope, fid)
    case = Case(
        court_id=filing.court_id,
        case_type_id=filing.case_type_id,
        case_number="DELIVERY-1",
        title="Protected delivery case",
        is_sealed=True,
        filed_date=datetime.now(UTC),
    )
    db.add(case)
    await db.flush()
    filing.case_id, filing.filing_type = case.id, "service_only"
    participants = []
    for uid, role in ((sender, ParticipantRole.PLAINTIFF), (receiver, ParticipantRole.DEFENDANT)):
        account = await db.get(User, uid)
        account.verified_email = account.email
        account.keycloak_id = f"synthetic-{uid}"
        participant = CaseParticipant(
            case_id=case.id,
            user_id=uid,
            party_name=account.full_name,
            role=role,
            is_active=True,
            access_enabled=True,
            reviewed_at=datetime.now(UTC),
        )
        db.add(participant)
        participants.append(participant)
    await db.flush()
    contact = ServiceContact(
        case_id=case.id,
        participant_id=participants[1].id,
        participant_snapshot=participant_snapshot(participants[1]),
        user_id=receiver,
        name="Other Filer",
        email="other@test.com",
        method="electronic",
        is_active=True,
        authority="Synthetic court order",
        reviewed_at=datetime.now(UTC),
        reviewer_id=staff,
        version=1,
    )
    documents = [
        stored_document(fid, document_type_code=code, title=title)
        for code, title in (
            ("MOTION", "Selected motion"),
            ("EXHIBIT", "Unselected exhibit"),
            ("FEE_WAIVER", "Private financial material"),
        )
    ]
    db.add_all([contact, *documents])
    await db.flush()
    await filing_service.submit_filing(db, fid)
    source = await db.scalar(
        select(FilingTransaction).where(
            FilingTransaction.filing_id == fid,
        )
    )
    data = {
        "source_transaction_id": source.id,
        "document_ids": [documents[0].id],
        "recipients": [{"contact_id": contact.id, "version": 1}],
        "reviewed": True,
    }
    return {
        "fid": fid,
        "sender": sender,
        "staff": staff,
        "receiver": receiver,
        "case": case,
        "participant": participants[1],
        "contact": contact,
        "documents": documents,
        "data": data,
    }


@pytest.fixture
async def delivery_case(db_session, api_client, stored_document, smtp_sink, monkeypatch):
    monkeypatch.setattr(settings, "service_delivery_enabled", True)
    fixture = await prepare_delivery(db_session, stored_document)
    api_client.headers["X-Demo-User-Id"] = str(fixture["sender"])
    return fixture


async def send(client, fixture, *, key=None):
    return await client.post(
        f"/api/v1/service/filings/{fixture['fid']}/deliveries",
        headers={"Idempotency-Key": key or str(uuid4())},
        json=fixture["data"],
    )


async def test_delivery_grants_only_selected_bytes_and_retains_recipient_acknowledgment(
    delivery_case,
    db_session,
    api_client,
):
    f = delivery_case
    options = await api_client.get(f"/api/v1/service/filings/{f['fid']}/options")
    assert options.status_code == 200, options.text
    assert [d["id"] for d in options.json()["documents"]] == [d.id for d in f["documents"][:2]]
    assert options.json()["recipients"][1]["issues"] == []
    key = str(uuid4())
    first, replay = await send(api_client, f, key=key), await send(api_client, f, key=key)
    assert first.status_code == 201, first.text
    assert first.json() == replay.json()
    recipient = await db_session.scalar(select(ServiceRecipient))
    path = f"/api/v1/service/deliveries/{recipient.id}"
    sent = await api_client.get(f"/api/v1/service/filings/{f['fid']}/deliveries")
    assert sent.json()["total"] == 1
    assert (await api_client.post(path + "/acknowledge")).status_code == 403
    api_client.headers["X-Demo-User-Id"] = str(f["receiver"])
    details = (await api_client.get(path)).json()
    assert details["contact"]["email"] == "other@test.com"
    assert len(details["documents"]) == 1 and "fee_waiver_requested" not in details
    assert (await api_client.get(f"/api/v1/filings/{f['fid']}/history")).status_code == 403
    for doc in f["documents"][1:]:
        assert (await api_client.get(f"{path}/documents/{doc.id}")).status_code == 404
    selected = f["documents"][0]
    assert (await api_client.get(f"/api/v1/documents/{selected.id}/download")).status_code == 403
    download = await api_client.get(f"{path}/documents/{selected.id}")
    assert download.status_code == 200 and download.content == b"Synthetic Selected motion"
    assert download.headers["cache-control"] == "private, no-store"
    for _ in range(2):
        assert (await api_client.post(path + "/acknowledge")).status_code == 200
    assert not (await api_client.get(path)).json()["can_acknowledge"]
    events = (await api_client.get(path + "/events")).json()["events"]
    assert [e["action"] for e in events] == ["acknowledged", "download_requested"]
    assert (await api_client.get(path + "/events?kind=email")).json()["events"][0][
        "action"
    ] == "queued"
    assert (await api_client.get("/api/v1/service/deliveries")).json()["total"] == 1
    # Revocation removes content access; the inbox discloses no sealed caption.
    f["participant"].access_enabled = False
    await db_session.flush()
    assert (await api_client.get(path)).status_code == 403
    assert (
        "Protected delivery case" not in (await api_client.get("/api/v1/service/deliveries")).text
    )


@pytest.mark.parametrize(
    "change", ["contact", "receipt", "private", "storage", "unreviewed", "disabled", "other_sender"]
)
async def test_invalid_delivery_does_not_queue_a_partial_package(
    delivery_case, db_session, api_client, change
):
    f = delivery_case
    if change == "contact":
        f["contact"].version += 1
    elif change == "receipt":
        f["data"]["source_transaction_id"] = str(uuid4())
    elif change == "private":
        f["data"]["document_ids"].append(f["documents"][2].id)
    elif change == "storage":
        document_service.upload_document(b"altered", f["documents"][0].file_key, "text/plain")
    elif change == "unreviewed":
        f["participant"].reviewed_at = None
    elif change == "disabled":
        settings.service_delivery_enabled = False
    elif change == "other_sender":
        api_client.headers["X-Demo-User-Id"] = str(f["receiver"])
    await db_session.flush()
    response = await send(api_client, f)
    expected = {"private": 422, "disabled": 503, "other_sender": 403}.get(change, 409)
    assert response.status_code == expected, response.text
    assert await db_session.scalar(select(func.count()).select_from(ServicePacket)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ServiceRecipient)) == 0


async def test_past_delivery_survives_email_change_but_cannot_be_retargeted(
    delivery_case, db_session, api_client
):
    f = delivery_case
    assert (await send(api_client, f)).status_code == 201
    recipient = await db_session.scalar(select(ServiceRecipient))
    path = f"/api/v1/service/deliveries/{recipient.id}"
    account = await db_session.get(User, f["receiver"])
    account.email = account.verified_email = "new@test.com"
    f["contact"].email, f["contact"].version = account.email, 2
    notice = await db_session.get(Notification, recipient.notification_id)
    notice.delivery_status = DeliveryStatus.FAILED
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(f["receiver"])
    assert (await api_client.get(path)).json()["contact"]["email"] == "other@test.com"
    assert (
        await api_client.post(f"/api/v1/notifications/{notice.id}/retry", json={"reason": "try"})
    ).status_code == 409
    api_client.headers["X-Demo-User-Id"] = str(f["sender"])
    retry = await api_client.post(path + "/retry", json={"reason": "try"})
    assert retry.status_code == 409 and "changed" in retry.text


async def test_delivered_contents_cannot_be_rewritten_or_reused_with_a_different_selection(
    delivery_case,
    db_session,
    api_client,
):
    f = delivery_case
    key = str(uuid4())
    assert (await send(api_client, f, key=key)).status_code == 201
    recipient = await db_session.scalar(select(ServiceRecipient))
    f["data"]["document_ids"] = [f["documents"][1].id]
    assert (await send(api_client, f, key=key)).status_code == 409
    document_service.upload_document(b"altered", f["documents"][0].file_key, "text/plain")
    api_client.headers["X-Demo-User-Id"] = str(f["receiver"])
    response = await api_client.get(
        f"/api/v1/service/deliveries/{recipient.id}/documents/{f['documents'][0].id}",
    )
    assert response.status_code == 409 and response.content != b"altered"


async def test_uncertain_alert_retry_requires_staff_and_keeps_the_same_package(
    delivery_case,
    db_session,
    api_client,
):
    f = delivery_case
    assert (await send(api_client, f)).status_code == 201
    recipient = await db_session.scalar(select(ServiceRecipient))
    notice = await db_session.get(Notification, recipient.notification_id)
    notice.delivery_status = DeliveryStatus.UNKNOWN
    await db_session.flush()
    path = f"/api/v1/service/deliveries/{recipient.id}"
    assert not (await api_client.get(path)).json()["can_retry"]
    assert (await api_client.post(path + "/retry", json={"reason": "Reviewed"})).status_code == 403
    api_client.headers["X-Demo-User-Id"] = str(f["staff"])
    assert (await api_client.get(path)).json()["can_retry"]
    result = await api_client.post(
        path + "/retry", json={"reason": "Relay logs checked; no acknowledgment"}
    )
    assert result.status_code == 200 and result.json()["delivery_status"] == "pending"
    assert await db_session.scalar(select(func.count()).select_from(ServicePacket)) == 1


@pytest.mark.parametrize("case_records", ["sqlite", "postgres"], indirect=True)
async def test_archive_keeps_delivery_contents_addresses_and_acknowledgment(
    case_records,
    smtp_sink,
    stored_document,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(settings, "service_delivery_enabled", True)
    async with case_records["sessions"].begin() as db:
        # Keep the pre-existing case as an exclusion check, with distinct accounts.
        for user in await db.scalars(select(User)):
            user.email = f"archive-{user.id}@test.com"
        await db.flush()
        f = await prepare_delivery(db, stored_document)
        packet = await create_packet(
            db, f["sender"], f["fid"], ServicePacketCreate(**f["data"]), str(uuid4())
        )
        recipient = await db.scalar(
            select(ServiceRecipient).where(ServiceRecipient.packet_id == packet.id)
        )
        db.add(
            ServiceEvent(
                service_recipient_id=recipient.id,
                action="acknowledged",
                actor_id=f["receiver"],
                actor_name="Other Filer",
                occurred_at=datetime.now(UTC),
                details={},
            )
        )
    while await email_delivery_service.deliver_next(case_records["sessions"]):
        pass
    async with case_records["sessions"].begin() as db:
        from app.api.service_deliveries import report_delivery_failure

        notice = await db.get(Notification, recipient.notification_id)
        assert notice.delivery_status == DeliveryStatus.SENT
        await report_delivery_failure(
            UUID(recipient.id),
            ServiceFailureReport(
                source="relay_notice",
                source_reference="Synthetic archived relay report",
                description="Mailbox rejected after relay acceptance",
                observed_at=datetime.now(UTC),
                expected_message_id=notice.email_message_id,
                expected_attempt_count=notice.attempt_count,
                reviewed=True,
            ),
            db,
            await db.get(User, f["staff"]),
            uuid4(),
        )
        contact = await db.get(ServiceContact, f["contact"].id)
        contact.email, contact.version = "changed@test.com", 2
    output = tmp_path / "delivery.zip"
    result = await case_export.export_case(f["case"].id, output)
    assert case_export.verify_archive(output, result["manifest_sha256"])["status"] == "verified"
    with ZipFile(output) as archive:
        saved = json.loads(archive.read("records/service_packets.jsonl"))
        assert saved["details"]["documents"][0]["id"] == f["documents"][0].id
        assert (
            json.loads(archive.read("records/service_recipients.jsonl"))["contact_snapshot"][
                "email"
            ]
            == "other@test.com"
        )
        assert (
            json.loads(archive.read("records/service_contacts.jsonl"))["email"]
            == "changed@test.com"
        )
        events = [
            json.loads(line) for line in archive.read("records/service_events.jsonl").splitlines()
        ]
        assert {event["action"] for event in events} == {"acknowledged", "failure_reported"}
        failure = next(event for event in events if event["action"] == "failure_reported")
        assert failure["details"]["source_reference"] == "Synthetic archived relay report"
        notices = [
            json.loads(line) for line in archive.read("records/notifications.jsonl").splitlines()
        ]
        assert any(
            notice["id"] == failure["details"]["sender_notification_id"] for notice in notices
        )


@pytest.mark.parametrize("outcome", ["accepted", "changed_contact", "unknown"])
async def test_service_outbox_uses_frozen_secure_link_and_rechecks_before_smtp(
    mail_sessions,
    smtp_sink,
    stored_document,
    monkeypatch,
    outcome,
):
    monkeypatch.setattr(settings, "service_delivery_enabled", True)
    async with mail_sessions.begin() as db:
        f = await prepare_delivery(db, stored_document)
        packet = await create_packet(
            db, f["sender"], f["fid"], ServicePacketCreate(**f["data"]), str(uuid4())
        )
        recipient = await db.scalar(
            select(ServiceRecipient).where(ServiceRecipient.packet_id == packet.id)
        )
        if outcome == "changed_contact":
            f["contact"].is_active = False
    smtp_sink["lose_reply"] = outcome == "unknown"
    while await email_delivery_service.deliver_next(mail_sessions):
        pass
    async with mail_sessions() as db:
        notice = await db.get(Notification, recipient.notification_id)
        assert (
            notice.delivery_status
            == {
                "accepted": DeliveryStatus.SENT,
                "changed_contact": DeliveryStatus.BLOCKED,
                "unknown": DeliveryStatus.UNKNOWN,
            }[outcome]
        )
        messages = [
            Parser(policy=policy.default).parsestr(message) for message in smtp_sink["messages"]
        ]
        service_messages = [
            message for message in messages if str(recipient.id) in message.get_content()
        ]
        assert len(service_messages) == (0 if outcome == "changed_contact" else 1)
        if service_messages:
            message = service_messages[0]
            body = message.get_content()
            assert f"/service/deliveries/{recipient.id}" in body
            assert "Protected delivery case" not in body and "Private financial" not in body
            assert message["To"] == "other@test.com"
        assert not await email_delivery_service.deliver_next(mail_sessions)


@pytest.mark.skipif(
    not os.getenv("MUEFS_TEST_POSTGRES_URL"), reason="Disposable PostgreSQL required"
)
@pytest.mark.parametrize("postgres_sessions", [False, True], indirect=True)
async def test_concurrent_delivery_replays_once_and_database_protects_evidence(
    postgres_sessions,
    smtp_sink,
    stored_document,
    monkeypatch,
):
    monkeypatch.setattr(settings, "service_delivery_enabled", True)
    async with postgres_sessions.begin() as db:
        f = await prepare_delivery(db, stored_document)
    key = str(uuid4())

    async def submit():
        async with postgres_sessions.begin() as db:
            packet = await create_packet(
                db, f["sender"], f["fid"], ServicePacketCreate(**f["data"]), key
            )
            return packet.id

    one, two = await asyncio.wait_for(asyncio.gather(submit(), submit()), 15)
    assert one == two
    async with postgres_sessions.begin() as db:
        from app.api.service_deliveries import sent_deliveries

        result = await sent_deliveries(f["fid"], db, await db.get(User, f["sender"]), page=1)
        assert result["total"] == 1 and result["deliveries"][0]["email"] == "other@test.com"
        assert await db.scalar(select(func.count()).select_from(ServiceRecipient)) == 1
        recipient = await db.scalar(select(ServiceRecipient))
        db.add(
            ServiceEvent(
                service_recipient_id=recipient.id,
                action="acknowledged",
                actor_id=f["receiver"],
                actor_name="Other Filer",
                occurred_at=datetime.now(UTC),
                details={},
            )
        )
    for table in ("service_packets", "service_recipients", "service_events"):
        for statement in (f"DELETE FROM {table}", f"UPDATE {table} SET id=id"):
            with pytest.raises(DBAPIError, match="append-only"):
                async with postgres_sessions.begin() as db:
                    await db.execute(text(statement))
