"""Portable case archives retain evidence, stay consistent, and fail atomically."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_STORED, ZipFile

import pytest
from alembic.config import Config
from sqlalchemy import select, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app import case_export
from app.config import settings
from app.models.audit import AuditLog
from app.models.case import Case, CaseParticipant, CaseStatus, ParticipantRole
from app.models.court_calendar import CourtCalendar
from app.models.document_public_copy import DocumentPublicCopy
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.notification import (
    DeliveryStatus,
    Notification,
    NotificationDeliveryEvent,
    NotificationType,
)
from app.models.payment import Payment, PaymentStatus
from app.models.user import User
from app.schemas.filing import FilingDocumentResponse
from app.services import document_service
from tests.test_document_publication import publication_pdf
from tests.test_filing_history import filing_fixture
from tests.test_s3_storage import s3_storage as s3_storage

POSTGRES_URL = os.getenv("MUEFS_TEST_POSTGRES_URL")
S3_ENDPOINT = os.getenv("MUEFS_TEST_S3_ENDPOINT")


@pytest.fixture
async def case_records(request, tmp_path, monkeypatch, stored_document):
    database = f"case_export_{uuid4().hex}"
    admin = None
    if getattr(request, "param", "sqlite") == "postgres":
        if not POSTGRES_URL:
            pytest.skip("MUEFS_TEST_POSTGRES_URL not configured")
        assert make_url(POSTGRES_URL).host in {"localhost", "127.0.0.1"}
        admin = create_async_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
        async with admin.connect() as connection:
            await connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
        url = make_url(POSTGRES_URL).set(database=database).render_as_string(hide_password=False)
    else:
        url = f"sqlite+aiosqlite:///{(tmp_path / 'records.db').as_posix()}"
    engine = create_async_engine(url)
    monkeypatch.setattr(settings, "database_url", url)
    # Object storage is independent of the database dialect during these snapshot tests.
    monkeypatch.setattr(document_service, "uses_local_storage", lambda: True)
    try:
        async with engine.connect() as connection:
            if connection.dialect.name == "sqlite":
                await connection.exec_driver_sql("PRAGMA journal_mode=WAL")
                await connection.commit()

            def migrate(sync_connection):
                config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
                config.set_main_option(
                    "script_location", str(Path(__file__).resolve().parents[1] / "alembic")
                )
                config.attributes["connection"] = sync_connection
                command.upgrade(config, "head")

            await connection.run_sync(migrate)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions.begin() as db:
            fid, filer, clerk, other = await filing_fixture(db)
            filing = await db.get(FilingEnvelope, fid)
            case = Case(
                court_id=filing.court_id,
                case_type_id=filing.case_type_id,
                case_number="SYNTHETIC-EXPORT-1",
                title="Private case original title",
                status=CaseStatus.OPEN,
                is_sealed=True,
                filed_date=datetime.now(UTC),
            )
            db.add(case)
            await db.flush()
            filing.case_id = case.id
            filing.status = FilingStatus.RETURNED
            filing.filing_description = "Original filing description"
            filing.submitted_at = datetime.now(UTC)
            filing.submission_count = 1
            original = stored_document(fid, title="Private original / unsafe .. title")
            prior = stored_document(fid, title="Superseded document")
            prior.removed_at = datetime.now(UTC)
            waiver = stored_document(
                fid, document_type_code="FEE_WAIVER_ORDER", title="Waiver order"
            )
            order = stored_document(fid, document_type_code="FILING_DATE_ORDER", title="Date order")
            documents = [original, prior, waiver, order]
            for doc in documents:
                doc.retained_at = datetime.now(UTC)
                doc.is_confidential = True
            db.add_all(documents)
            await db.flush()
            copies = []
            payload = publication_pdf("Synthetic public copy")
            for index in range(2):
                key = f"public-copies/{index}.pdf"
                document_service.upload_document(payload, key, "application/pdf")
                copy = DocumentPublicCopy(
                    document_id=original.id,
                    created_by=clerk,
                    title=f"Public copy {index}",
                    file_key=key,
                    file_size_bytes=len(payload),
                    mime_type="application/pdf",
                    page_count=1,
                    is_text_searchable=True,
                    sha256_hash=hashlib.sha256(payload).hexdigest(),
                    pii_warnings=[],
                )
                db.add(copy)
                copies.append(copy)
            await db.flush()
            original.public_copy_id = copies[0].id
            receipt = FilingTransaction(
                filing_id=fid,
                submission_number=1,
                event_type="submitted",
                actor_id=filer,
                actor_name="Original filer",
                occurred_at=datetime.now(UTC),
                details={
                    "documents": [
                        FilingDocumentResponse.model_validate(doc).model_dump(mode="json")
                        for doc in (original, prior)
                    ]
                },
            )
            db.add(receipt)
            db.add(
                FilingTransaction(
                    filing_id=fid,
                    submission_number=1,
                    event_type="public_copy_published",
                    actor_id=clerk,
                    actor_name="Original clerk",
                    occurred_at=datetime.now(UTC),
                    details={
                        "public_copy": {
                            "id": copies[0].id,
                            "document_id": original.id,
                            "sha256_hash": copies[0].sha256_hash,
                            "file_size_bytes": len(payload),
                        }
                    },
                )
            )
            payment = Payment(
                envelope_id=fid,
                payer_id=filer,
                amount_cents=750,
                status=PaymentStatus.COMPLETED,
                is_simulated=True,
                fee_basis={"source": "court", "total_cents": 750},
            )
            db.add(payment)
            db.add(
                CaseParticipant(
                    case_id=case.id,
                    user_id=filer,
                    role=ParticipantRole.ATTORNEY_PLAINTIFF,
                    party_name="Counsel",
                    represented_party_name="Private party",
                    contact_email="private-contact@example.test",
                )
            )
            db.add(
                CourtCalendar(
                    court_id=case.court_id,
                    timezone="America/Detroit",
                    valid_from=date(2026, 1, 1),
                    valid_through=date(2026, 12, 31),
                    closed_dates={},
                    authority_reference="Synthetic approved calendar",
                    published_by=clerk,
                    published_at=datetime.now(UTC),
                )
            )
            db.add(
                AuditLog(
                    user_id=clerk,
                    action="case.participant_updated",
                    entity_type="case",
                    entity_id=case.id,
                    details={"reason": "Retained private audit reason"},
                )
            )
            notice = Notification(
                recipient_id=filer,
                filing_envelope_id=fid,
                notification_type=NotificationType.CASE_UPDATE,
                subject="Private case notice",
                body="Retained message",
                delivery_status=DeliveryStatus.SENT,
                email_message="Original synthetic MIME message",
            )
            db.add(notice)
            await db.flush()
            filing.payment_id = payment.id
            db.add(
                NotificationDeliveryEvent(
                    notification_id=notice.id,
                    attempt_number=1,
                    outcome="sent",
                    occurred_at=datetime.now(UTC),
                    detail="Synthetic relay accepted",
                    message="Original synthetic MIME message",
                )
            )
            outsider_case = Case(
                court_id=case.court_id,
                case_type_id=case.case_type_id,
                case_number="OTHER-CASE",
                title="Other case must stay out",
                filed_date=datetime.now(UTC),
            )
            db.add(outsider_case)
            await db.flush()
            outsider_filing = FilingEnvelope(
                case_id=outsider_case.id,
                court_id=case.court_id,
                case_type_id=case.case_type_id,
                filer_id=other,
                case_title="Other filing must stay out",
            )
            db.add(outsider_filing)
            await db.flush()
            db.add(stored_document(outsider_filing.id, title="Other case bytes"))
            user = await db.get(User, filer)
            user.keycloak_id = "private-identity-subject"
        yield {
            "case": case,
            "filing": filing,
            "documents": documents,
            "copies": copies,
            "receipt": receipt,
            "sessions": sessions,
            "storage": tmp_path,
            "url": url,
        }
    finally:
        await engine.dispose()
        if admin:
            async with admin.connect() as connection:
                await connection.exec_driver_sql(f'DROP DATABASE "{database}"')
            await admin.dispose()


@pytest.mark.parametrize("case_records", ["sqlite", "postgres"], indirect=True)
async def test_export_retains_service_instructions_and_their_prior_destination(
    case_records, tmp_path,
):
    from httpx import ASGITransport, AsyncClient

    from app.database import get_db
    from app.main import app
    from app.models.user import CourtRole, UserCourtRole

    sessions, case = case_records["sessions"], case_records["case"]
    async with sessions.begin() as db:
        participant = await db.scalar(select(CaseParticipant).where(
            CaseParticipant.case_id == case.id,
        ))
        participant.reviewed_at = datetime.now(UTC)
        clerk = await db.scalar(select(UserCourtRole.user_id).where(
            UserCourtRole.court_id == case.court_id, UserCourtRole.role == CourtRole.CLERK,
        ))

    async def database():
        async with sessions.begin() as db:
            yield db

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test",
                               headers={"X-Demo-User-Id": str(clerk)}) as client:
            for version, address in enumerate(["Original service address", "Corrected address"]):
                response = await client.put(
                    f"/api/v1/cases/{case.id}/participants/{participant.id}/service-contact",
                    json={
                        "method": "mail",
                        "address": address,
                        "authority": "Reviewed address notice",
                        "reason": "Court-approved address correction",
                        "expected_version": version,
                        "expected_participant_version": 0,
                    },
                )
                assert response.status_code == 200, response.text
    finally:
        app.dependency_overrides.pop(get_db, None)
    output = tmp_path / "service-history.zip"
    result = await case_export.export_case(case.id, output)
    assert case_export.verify_archive(output, result["manifest_sha256"])["status"] == "verified"
    with ZipFile(output) as archive:
        contact = json.loads(archive.read("records/service_contacts.jsonl"))
        assert contact["address"] == "Corrected address" and contact["version"] == 2
        assert contact["reviewer_id"] == clerk
        events = [json.loads(line) for line in archive.read("records/audit_log.jsonl").splitlines()]
        changes = [event for event in events if event["action"] == "case.service_contact_changed"]
        assert len(changes) == 2
        assert changes[1]["details"]["before"]["address"] == "Original service address"
        assert changes[1]["details"]["after"]["address"] == "Corrected address"


@pytest.mark.parametrize("case_records", ["sqlite", "postgres"], indirect=True)
async def test_complete_archive_retains_private_evidence_without_changing_records(
    case_records, tmp_path
):
    data, output = case_records, tmp_path / "case.zip"
    result = await case_export.export_case(data["case"].id, output)
    verified = case_export.verify_archive(output, result["manifest_sha256"])
    assert verified["status"] == "verified"
    with ZipFile(output) as archive:

        def records(table):
            return [
                json.loads(line) for line in archive.read(f"records/{table}.jsonl").splitlines()
            ]

        assert len(records("cases")) == len(records("filing_envelopes")) == 1
        assert len(records("filing_documents")) == 4
        assert len(records("document_public_copies")) == 2
        assert records("cases")[0]["is_sealed"] is True
        assert records("filing_envelopes")[0]["status"] == "returned"
        assert records("case_participants")[0]["contact_email"] == "private-contact@example.test"
        assert records("payments")[0]["fee_basis"] == {"source": "court", "total_cents": 750}
        assert (
            records("notification_delivery_events")[0]["message"]
            == "Original synthetic MIME message"
        )
        assert records("audit_log")[0]["details"]["reason"] == "Retained private audit reason"
        assert records("court_calendars")[0]["authority_reference"] == "Synthetic approved calendar"
        assert "keycloak_id" not in records("users")[0]
        assert b"private-identity-subject" not in archive.read("records/users.jsonl")
        assert len(records("users")) == 2
        for row in [*records("filing_documents"), *records("document_public_copies")]:
            assert (
                archive.read(row["object_path"]) == (data["storage"] / row["file_key"]).read_bytes()
            )
            assert archive.getinfo(row["object_path"]).compress_type == ZIP_STORED
        # Two separate public-copy keys with identical contents occupy one archive object.
        assert len([name for name in archive.namelist() if name.startswith("objects/")]) == 5
        receipt = next(
            row for row in records("filing_transactions") if row["id"] == data["receipt"].id
        )
        assert receipt["details"] == data["receipt"].details
    async with data["sessions"]() as db:
        assert (
            await db.scalar(select(Case.title).where(Case.id == data["case"].id))
            == data["case"].title
        )
        assert len(list(await db.scalars(select(AuditLog)))) == 1
    before = output.read_bytes()
    with pytest.raises(case_export.CaseExportError, match="already exists"):
        await case_export.export_case(data["case"].id, output)
    assert output.read_bytes() == before and not list(tmp_path.glob(".case-export-*"))


@pytest.mark.parametrize(
    "failure", ["missing_file", "changed_file", "inactive_copy", "receipt", "outside_payment"]
)
async def test_incomplete_evidence_never_publishes_an_archive(case_records, tmp_path, failure):
    data, output = case_records, tmp_path / "incomplete.zip"
    if failure == "outside_payment":
        async with data["sessions"].begin() as db:
            other_filing = await db.scalar(
                select(FilingEnvelope).where(
                    FilingEnvelope.case_id != data["case"].id,
                )
            )
            payment = Payment(
                envelope_id=other_filing.id,
                payer_id=other_filing.filer_id,
                amount_cents=750,
                status=PaymentStatus.COMPLETED,
            )
            db.add(payment)
            await db.flush()
            await db.execute(
                update(FilingEnvelope)
                .where(FilingEnvelope.id == data["filing"].id)
                .values(payment_id=payment.id)
            )
    elif failure == "receipt":
        async with data["sessions"].begin() as db:
            db.add(
                FilingTransaction(
                    filing_id=data["filing"].id,
                    submission_number=2,
                    event_type="submitted",
                    actor_id=data["filing"].filer_id,
                    actor_name="Filer",
                    occurred_at=datetime.now(UTC),
                    details={"documents": []},
                )
            )
    else:
        doc = data["copies"][1] if failure == "inactive_copy" else data["documents"][1]
        path = data["storage"] / doc.file_key
        if failure == "missing_file":
            path.unlink()
        else:
            path.write_bytes(b"Changed retained bytes")
    with pytest.raises((case_export.CaseExportError, OSError)):
        await case_export.export_case(data["case"].id, output)
    assert not output.exists() and not list(tmp_path.glob(".case-export-*"))


@pytest.mark.parametrize("case_records", ["sqlite", "postgres"], indirect=True)
async def test_archive_uses_one_snapshot_while_records_change(case_records, tmp_path, monkeypatch):
    data = case_records
    inspect = case_export.inspect_receipts

    async def change_after_snapshot(connection, **kwargs):
        async with data["sessions"].begin() as db:
            await db.execute(
                update(Case).where(Case.id == data["case"].id).values(title="Later title")
            )
            await db.execute(
                update(FilingEnvelope)
                .where(FilingEnvelope.id == data["filing"].id)
                .values(filing_description="Later description")
            )
        async for row in inspect(connection, **kwargs):
            yield row

    monkeypatch.setattr(case_export, "inspect_receipts", change_after_snapshot)
    output = tmp_path / "consistent.zip"
    await case_export.export_case(data["case"].id, output)
    with ZipFile(output) as archive:
        assert (
            json.loads(archive.read("records/cases.jsonl"))["title"]
            == "Private case original title"
        )
        assert (
            json.loads(archive.read("records/filing_envelopes.jsonl"))["filing_description"]
            == "Original filing description"
        )
    async with data["sessions"]() as db:
        assert (
            await db.scalar(select(Case.title).where(Case.id == data["case"].id)) == "Later title"
        )


async def test_cli_export_and_offline_verification_detect_modified_archives(case_records, tmp_path):
    data, output = case_records, tmp_path / "cli.zip"
    env = {**os.environ, "DATABASE_URL": data["url"], "LOCAL_STORAGE_PATH": str(data["storage"])}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.case_export",
            "export",
            "--case-id",
            str(data["case"].id),
            "--output",
            str(output),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    fingerprint = json.loads(result.stdout)["manifest_sha256"]
    env["DATABASE_URL"] = "postgresql+asyncpg://offline:unused@127.0.0.1:1/unavailable"
    verified = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.case_export",
            "verify",
            str(output),
            "--manifest-sha256",
            fingerprint,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert verified.returncode == 0, verified.stderr
    altered = tmp_path / "altered.zip"
    with ZipFile(output) as source, ZipFile(altered, "w") as target:
        for info in source.infolist():
            target.writestr(
                info.filename,
                b"Altered" if info.filename.startswith("objects/") else source.read(info),
            )
    with pytest.raises(case_export.CaseExportError, match="fingerprint"):
        case_export.verify_archive(altered, fingerprint)
    with pytest.raises(case_export.CaseExportError, match="separately retained"):
        case_export.verify_archive(output, "0" * 64)


@pytest.mark.skipif(not S3_ENDPOINT, reason="MUEFS_TEST_S3_ENDPOINT not configured")
async def test_s3_objects_are_streamed_closed_and_verified_even_when_contents_repeat(
    case_records,
    s3_storage,
    tmp_path,
    monkeypatch,
):
    data = case_records
    client, bucket = s3_storage
    sources = [*data["documents"], *data["copies"]]
    for doc in sources:
        client.put_object(
            Bucket=bucket, Key=doc.file_key, Body=(data["storage"] / doc.file_key).read_bytes()
        )
    monkeypatch.setattr(settings, "database_url", data["url"])
    monkeypatch.setattr(document_service, "uses_local_storage", lambda: False)
    download = document_service.download_document
    reads, closed = [], []

    def bounded_download(key):
        stream = download(key)
        reads.append(key)

        class BoundedReader:
            def read(self, size):
                assert 0 < size <= 64 * 1024
                return stream.read(size)

            def close(self):
                stream.close()
                closed.append(key)

        return BoundedReader()

    monkeypatch.setattr(document_service, "download_document", bounded_download)
    output = tmp_path / "s3.zip"
    result = await case_export.export_case(data["case"].id, output)
    assert sorted(reads) == sorted(closed) == sorted(doc.file_key for doc in sources)
    assert case_export.verify_archive(output, result["manifest_sha256"])["status"] == "verified"
    client.put_object(Bucket=bucket, Key=data["copies"][1].file_key, Body=b"Changed copy bytes")
    failed = tmp_path / "s3-corrupt.zip"
    with pytest.raises(case_export.CaseExportError, match="fingerprint"):
        await case_export.export_case(data["case"].id, failed)
    assert sorted(reads) == sorted(closed)
    assert not failed.exists() and not list(tmp_path.glob(".case-export-*"))


async def test_verifier_rejects_unlisted_entries_without_extracting_files(
    case_records, tmp_path, monkeypatch,
):
    output = tmp_path / "unlisted.zip"
    await case_export.export_case(case_records["case"].id, output)
    with ZipFile(output, "a") as archive:
        archive.writestr("../outside.txt", b"Do not extract")
    extractions = []

    def refuse_extraction(_archive, *args, **kwargs):
        extractions.append(args)
        raise AssertionError("Verification extracted archive entries")

    # ZipFile strips "..", so extraction would write beside the archive, not above it.
    monkeypatch.setattr(ZipFile, "extract", refuse_extraction)
    monkeypatch.setattr(ZipFile, "extractall", refuse_extraction)
    files_before = sorted(tmp_path.rglob("*"))
    with pytest.raises(case_export.CaseExportError, match="contents"):
        case_export.verify_archive(output)
    assert extractions == []
    assert sorted(tmp_path.rglob("*")) == files_before


async def test_simultaneous_exports_cannot_overwrite_one_another(case_records, tmp_path):
    output = tmp_path / "shared-destination.zip"
    results = await asyncio.gather(
        case_export.export_case(case_records["case"].id, output),
        case_export.export_case(case_records["case"].id, output),
        return_exceptions=True,
    )
    completed = [result for result in results if isinstance(result, dict)]
    assert len(completed) == 1
    assert any(
        isinstance(result, (FileExistsError, case_export.CaseExportError)) for result in results
    )
    assert (
        case_export.verify_archive(output, completed[0]["manifest_sha256"])["status"] == "verified"
    )
    assert not list(tmp_path.glob(".case-export-*"))
