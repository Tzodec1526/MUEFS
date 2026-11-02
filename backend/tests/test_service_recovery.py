import asyncio
import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from io import StringIO
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, select, text, update

from app import case_export
from app.config import settings
from app.models.case import CaseParticipant, ParticipantRole
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.notification import Notification, NotificationType, ServiceContact
from app.models.service_delivery import ServicePacket, ServiceRecipient
from app.models.user import User, UserType
from app.readonly_database import read_only_connection
from app.schemas.service_delivery import ServicePacketCreate
from app.services.case_participant_service import participant_snapshot
from app.services.service_delivery_service import create_packet
from app.storage_audit import inspect_service_packets, run_audit
from tests.test_case_export import case_records as case_records
from tests.test_email_delivery import smtp_sink as smtp_sink
from tests.test_service_deliveries import prepare_delivery


@pytest.fixture
async def service_records(case_records, stored_document, smtp_sink, monkeypatch):
    monkeypatch.setattr(settings, "service_delivery_enabled", True)
    async with case_records["sessions"].begin() as db:
        for user in await db.scalars(select(User)):
            user.email = f"archive-{user.id}@test.com"
        await db.flush()
        data = await prepare_delivery(db, stored_document)
        user = User(
            email="second@example.com", verified_email="second@example.com",
            keycloak_id="second-recovery", first_name="Second", last_name="Recipient",
            user_type=UserType.SELF_REPRESENTED,
        )
        db.add(user)
        await db.flush()
        participant = CaseParticipant(
            case_id=data["case"].id, user_id=user.id, party_name=user.full_name,
            role=ParticipantRole.DEFENDANT, is_active=True, access_enabled=True,
            reviewed_at=datetime.now(UTC),
        )
        db.add(participant)
        await db.flush()
        contact = ServiceContact(
            case_id=data["case"].id, user_id=user.id, name=user.full_name, email=user.email,
            method="electronic", participant_id=participant.id,
            participant_snapshot=participant_snapshot(participant), is_active=True,
            authority="Synthetic reviewed instructions", version=1, reviewed_at=datetime.now(UTC),
        )
        db.add(contact)
        await db.flush()
        data["data"]["recipients"].append({"contact_id": contact.id, "version": 1})
        data["data"]["document_ids"].append(data["documents"][1].id)
        packet = await create_packet(
            db, data["sender"], data["fid"], ServicePacketCreate(**data["data"]), str(uuid4()),
        )
        recipient = await db.scalar(select(ServiceRecipient).where(
            ServiceRecipient.packet_id == packet.id,
            ServiceRecipient.recipient_id == data["receiver"],
        ))
    return {
        **case_records, **data, "packet": packet, "recipient": recipient,
        "other_case": case_records["case"], "other_filing": case_records["filing"],
    }


@asynccontextmanager
async def damaged_restore(db, model, operation="update"):
    table = model.__tablename__
    postgres = db.bind.dialect.name == "postgresql"
    if postgres:
        await db.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {table}_append_only"))
    else:
        name = f"{table}_no_{operation}"
        ddl = await db.scalar(
            text("SELECT sql FROM sqlite_master WHERE name=:name"), {"name": name},
        )
        assert ddl
        await db.execute(text(f"DROP TRIGGER {name}"))
    try:
        yield
    finally:
        if postgres:
            await db.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {table}_append_only"))
        else:
            await db.execute(text(ddl))


@pytest.mark.parametrize("case_records", ["sqlite", "postgres"], indirect=True)
@pytest.mark.parametrize("damage, expected", [
    ("empty_manifest", "invalid_manifest"),
    ("duplicate_document", "invalid_manifest"),
    ("altered_document", "delivery_mismatch"),
    ("lost_document", "delivery_mismatch"),
    ("source", "delivery_mismatch"),
    ("case", "delivery_mismatch"),
    ("lost_recipient", "delivery_mismatch"),
    ("snapshot_account", "invalid_manifest"),
    ("snapshot_version", "invalid_manifest"),
    ("snapshot_shape", "invalid_manifest"),
    ("snapshot_email", "delivery_mismatch"),
    ("notice_case", "delivery_mismatch"),
    ("notice_recipient", "delivery_mismatch"),
    ("notice_type", "delivery_mismatch"),
    ("contact_version", "invalid_manifest"),
    ("contact_case", "delivery_mismatch"),
])
async def test_corrupt_delivery_cannot_be_reported_or_exported_as_complete(
    service_records, tmp_path, damage, expected,
):
    data = service_records
    packet, recipient = data["packet"], data["recipient"]
    async with data["sessions"].begin() as db:
        if damage in ("empty_manifest", "duplicate_document", "altered_document", "lost_document"):
            details = deepcopy(packet.details)
            if damage == "empty_manifest":
                details["documents"] = []
            elif damage == "duplicate_document":
                details["documents"] = [details["documents"][0]] * 2
            elif damage == "altered_document":
                details["documents"][0]["sha256_hash"] = "0" * 64
            else:
                details["documents"].pop()
            async with damaged_restore(db, ServicePacket):
                await db.execute(update(ServicePacket).where(
                    ServicePacket.id == packet.id,
                ).values(details=details))
        elif damage in ("source", "case"):
            values = (
                {"source_transaction_id": data["receipt"].id} if damage == "source"
                else {"case_id": data["other_case"].id}
            )
            async with damaged_restore(db, ServicePacket):
                await db.execute(update(ServicePacket).where(ServicePacket.id == packet.id)
                                 .values(**values))
        elif damage == "lost_recipient":
            async with damaged_restore(db, ServiceRecipient, "delete"):
                await db.execute(
                    delete(ServiceRecipient).where(ServiceRecipient.id == recipient.id)
                )
        elif damage.startswith("snapshot"):
            snapshot = deepcopy(recipient.contact_snapshot)
            if damage == "snapshot_account":
                snapshot["user_id"] = data["sender"]
            elif damage == "snapshot_version":
                snapshot["version"] = True
            elif damage == "snapshot_email":
                snapshot["email"] = "swapped@example.com"
            else:
                snapshot = []
            async with damaged_restore(db, ServiceRecipient):
                await db.execute(update(ServiceRecipient).where(ServiceRecipient.id == recipient.id)
                                 .values(contact_snapshot=snapshot))
        elif damage.startswith("notice"):
            values = {
                "notice_case": {"filing_envelope_id": data["other_filing"].id},
                "notice_recipient": {"recipient_id": data["sender"]},
                "notice_type": {"notification_type": NotificationType.CASE_UPDATE},
            }[damage]
            await db.execute(
                update(Notification).where(Notification.id == recipient.notification_id)
                .values(**values)
            )
        else:
            values = {"version": 0} if damage == "contact_version" else {
                "case_id": data["other_case"].id,
            }
            await db.execute(update(ServiceContact).where(ServiceContact.id == recipient.contact_id)
                             .values(**values))
    output = StringIO()
    assert await run_audit(output, court_id=data["case"].court_id) == 1
    report = [json.loads(line) for line in output.getvalue().splitlines()]
    assert report[0]["schema_version"] == 2
    assert any(row.get("id") in (packet.id, recipient.id)
               and row.get("status") == expected for row in report)
    assert report[-1]["complete"] and report[-1]["exit_code"] == 1
    assert "other@test.com" not in output.getvalue()
    assert "Protected delivery case" not in output.getvalue()
    target = tmp_path / "damaged-delivery.zip"
    with pytest.raises(case_export.CaseExportError, match="retained"):
        await case_export.export_case(data["case"].id, target)
    assert not target.exists() and not list(tmp_path.glob(".case-export-*"))
    if damage in ("source", "case", "notice_case", "contact_case"):
        with pytest.raises(case_export.CaseExportError, match="retained"):
            await case_export.export_case(data["other_case"].id, target)


@pytest.mark.parametrize("case_records", ["sqlite", "postgres"], indirect=True)
async def test_old_delivery_survives_later_contact_and_filing_changes(service_records, tmp_path):
    data = service_records
    async with data["sessions"].begin() as db:
        contact = await db.get(ServiceContact, data["contact"].id)
        contact.email = "changed@example.com"
        contact.version += 1
        contact.is_active = False
        participant = await db.get(CaseParticipant, contact.participant_id)
        participant.is_active = participant.access_enabled = False
        filing = await db.get(FilingEnvelope, data["fid"])
        filing.status = FilingStatus.RETURNED
        filing.submission_count += 1
        filing.case_title = "Later case caption"
    output = StringIO()
    assert await run_audit(output) == 0
    report = [json.loads(line) for line in output.getvalue().splitlines()]
    assert report[-1]["checked"]["service_packet"] == 1
    assert report[-1]["checked"]["service_recipient"] == 2
    target = tmp_path / "historical-delivery.zip"
    result = await case_export.export_case(data["case"].id, target)
    assert case_export.verify_archive(target, result["manifest_sha256"])["status"] == "verified"


async def test_missing_packet_or_source_is_detected_in_an_incomplete_sqlite_restore(
    service_records, tmp_path,
):
    data = service_records
    async with data["sessions"].begin() as db:
        async with damaged_restore(db, FilingTransaction, "delete"):
            await db.execute(delete(FilingTransaction).where(
                FilingTransaction.id == data["packet"].source_transaction_id,
            ))
    async with read_only_connection(data["url"]) as connection:
        report = [row async for row in inspect_service_packets(connection, case_id=data["case"].id)]
    assert any(row["status"] == "missing_metadata" for row in report)
    async with data["sessions"].begin() as db:
        async with damaged_restore(db, ServicePacket, "delete"):
            await db.execute(delete(ServicePacket).where(ServicePacket.id == data["packet"].id))
    output = StringIO()
    assert await run_audit(output, court_id=data["case"].court_id) == 1
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert sum(row.get("kind") == "service_recipient" and row.get("status") == "missing_metadata"
               for row in rows) == 2
    with pytest.raises(case_export.CaseExportError, match="retained"):
        await case_export.export_case(data["case"].id, tmp_path / "orphaned.zip")


@pytest.mark.parametrize("case_records", ["sqlite", "postgres"], indirect=True)
async def test_delivery_audit_pages_without_loading_messages_or_rereading_storage(
    service_records, monkeypatch,
):
    data = service_records
    async with data["sessions"].begin() as db:
        for _ in range(30):
            await create_packet(
                db, data["sender"], data["fid"], ServicePacketCreate(**data["data"]), str(uuid4()),
            )
    def unexpected_read(*args):
        pytest.fail("Delivery-reference validation reread stored bytes")
    from app.services import document_service
    monkeypatch.setattr(document_service, "stored_integrity", unexpected_read)
    statements = []
    def record(_conn, _cursor, sql, *_args):
        if sql.lstrip().upper().startswith("SELECT"):
            statements.append(sql)
    async with read_only_connection(data["url"]) as connection:
        event.listen(connection.sync_connection, "before_cursor_execute", record)
        report = [row async for row in inspect_service_packets(connection)]
    assert len(report) == 31 + 62
    assert all(row["status"] == "metadata_consistent" for row in report)
    assert all(len(row["selection_sha256" if row["kind"] == "service_packet"
                       else "contact_sha256"]) == 64 for row in report)
    assert len(statements) <= 8
    assert all("email_message" not in sql for sql in statements)


async def test_undecodable_restore_fails_without_disclosing_private_values(
    service_records, tmp_path,
):
    data = service_records
    private_value = "private-corrupt-destination@example.com"
    async with data["sessions"].begin() as db:
        await db.execute(text("UPDATE service_contacts SET method=:value WHERE id=:id"), {
            "value": private_value, "id": data["contact"].id,
        })
    output = StringIO()
    assert await run_audit(output) == 2
    report = [json.loads(line) for line in output.getvalue().splitlines()]
    assert report[-1]["complete"] is False
    assert private_value not in output.getvalue()
    target = tmp_path / "undecodable.zip"
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "app.case_export", "export",
         "--case-id", str(data["case"].id), "--output", str(target)],
        env={**os.environ, "DATABASE_URL": data["url"],
             "LOCAL_STORAGE_PATH": str(data["storage"])},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    assert json.loads(result.stderr)["status"] == "failed"
    assert private_value not in result.stderr + result.stdout
    assert not target.exists()
