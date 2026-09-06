"""Audit restored bytes and receipt references without repairing or exposing records."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.models.document_public_copy import DocumentPublicCopy
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.services import document_service
from app.storage_audit import run_audit
from tests.test_document_publication import publication_pdf
from tests.test_filing_history import filing_fixture


@pytest.fixture
async def restored_records(tmp_path, monkeypatch, stored_document):
    path = tmp_path / "restored collection #1.db"
    url = f"sqlite+aiosqlite:///{path.as_posix()}"
    monkeypatch.setattr(settings, "database_url", url)
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as db:
        fid, filer, clerk, _other = await filing_fixture(db)
        filing = await db.get(FilingEnvelope, fid)
        filing.status = FilingStatus.RETURNED
        filing.submitted_at = datetime.now(UTC)
        original = stored_document(fid, title="Private original")
        old = stored_document(fid, title="Private previous attachment")
        old.removed_at = old.retained_at = datetime.now(UTC)
        order = stored_document(fid, document_type_code="FEE_WAIVER_ORDER", title="Private order")
        order.is_confidential = True
        db.add_all([original, old, order])
        await db.flush()
        copies = []
        for i in range(2):
            payload = publication_pdf(f"Synthetic retained copy {i}")
            key = f"public-copies/private-copy-{i}.pdf"
            document_service.upload_document(payload, key, "application/pdf")
            copy = DocumentPublicCopy(
                document_id=original.id,
                created_by=clerk,
                title=f"Private copy {i}",
                file_key=key,
                mime_type="application/pdf",
                page_count=1,
                is_text_searchable=True,
                file_size_bytes=len(payload),
                sha256_hash=hashlib.sha256(payload).hexdigest(),
                pii_warnings=[],
            )
            db.add(copy)
            copies.append(copy)
        transaction = FilingTransaction(
            filing_id=fid,
            submission_number=1,
            event_type="submitted",
            actor_id=filer,
            actor_name="Private filer",
            occurred_at=datetime.now(UTC),
            details={
                "documents": [
                    {
                        "id": doc.id,
                        "sha256_hash": doc.sha256_hash,
                        "file_size_bytes": doc.file_size_bytes,
                    }
                    for doc in (original, old)
                ]
            },
        )
        db.add(transaction)
        await db.flush()
        db.add_all(
            [
                FilingTransaction(
                    filing_id=fid,
                    submission_number=1,
                    event_type="waiver_granted",
                    actor_id=clerk,
                    actor_name="Private clerk",
                    occurred_at=datetime.now(UTC),
                    details={
                        "documents": [
                            {
                                "id": order.id,
                                "sha256_hash": order.sha256_hash,
                                "file_size_bytes": order.file_size_bytes,
                            }
                        ]
                    },
                ),
                FilingTransaction(
                    filing_id=fid,
                    submission_number=1,
                    event_type="public_copy_published",
                    actor_id=clerk,
                    actor_name="Private clerk",
                    occurred_at=datetime.now(UTC),
                    details={
                        "public_copy": {
                            "id": copies[0].id,
                            "document_id": original.id,
                            "sha256_hash": copies[0].sha256_hash,
                            "file_size_bytes": copies[0].file_size_bytes,
                        }
                    },
                ),
            ]
        )
    try:
        yield {
            "path": path,
            "url": url,
            "sessions": sessions,
            "filing": filing,
            "original": original,
            "old": old,
            "order": order,
            "copies": copies,
            "receipt": transaction,
            "storage": tmp_path,
        }
    finally:
        await engine.dispose()


async def test_complete_audit_includes_archived_documents_orders_and_inactive_copies(
    restored_records,
):
    data = restored_records
    before = data["path"].read_bytes()
    output = StringIO()
    assert await run_audit(output) == 0
    report = [json.loads(line) for line in output.getvalue().splitlines()]
    assert report[-1]["complete"]
    assert report[-1]["checked"] == {
        "document": 3,
        "public_copy": 2,
        "receipt_document": 3,
        "receipt_public_copy": 1,
    }
    assert report[-1]["results"] == {"verified": 5, "metadata_consistent": 4}
    assert data["path"].read_bytes() == before
    assert "Private" not in output.getvalue()
    assert data["original"].file_key not in output.getvalue()
    assert str(data["path"]) not in output.getvalue()


@pytest.mark.parametrize(
    "damage, expected",
    [
        ("missing_file", "missing"),
        ("copy_corruption", "mismatch"),
        ("metadata_and_bytes", "receipt_mismatch"),
        ("missing_row", "missing_metadata"),
        ("invalid_hash", "invalid_metadata"),
        ("path_traversal", "invalid_reference"),
        ("storage_outage", "unavailable"),
    ],
)
async def test_audit_reports_discrepancies_and_never_repairs_them(
    restored_records,
    monkeypatch,
    damage,
    expected,
):
    data = restored_records
    path = data["storage"] / data["old"].file_key
    async with data["sessions"].begin() as db:
        old = await db.get(FilingDocument, data["old"].id)
        if damage == "missing_file":
            path.unlink()
        elif damage == "copy_corruption":
            path = data["storage"] / data["copies"][1].file_key
            content = path.read_bytes()
            path.write_bytes(b"X" + content[1:])
        elif damage == "metadata_and_bytes":
            content = b"Changed after the original receipt"
            path.write_bytes(content)
            old.sha256_hash = hashlib.sha256(content).hexdigest()
            old.file_size_bytes = len(content)
        elif damage == "missing_row":
            await db.delete(old)
        elif damage == "invalid_hash":
            old.sha256_hash = "invented"
        elif damage == "path_traversal":
            old.file_key = "../private-outside-storage.txt"
        else:
            from botocore.exceptions import EndpointConnectionError

            def unavailable(*args):
                raise EndpointConnectionError(
                    endpoint_url="http://secret-operator:secret@local.test"
                )

            monkeypatch.setattr(document_service, "download_document", unavailable)
    before_db = data["path"].read_bytes()
    before_file = path.read_bytes() if path.exists() else None
    output = StringIO()
    assert await run_audit(output) == 1
    report = [json.loads(line) for line in output.getvalue().splitlines()]
    assert report[-1]["complete"]
    assert report[-1]["results"][expected] >= 1
    assert data["path"].read_bytes() == before_db
    assert (path.read_bytes() if path.exists() else None) == before_file
    assert "secret" not in output.getvalue()
    assert "Private" not in output.getvalue()


async def test_audit_rejects_unknown_court_and_missing_database(restored_records, monkeypatch):
    output = StringIO()
    assert await run_audit(output, court_id=999999) == 2
    assert json.loads(output.getvalue().splitlines()[-1])["complete"] is False
    absent = restored_records["path"].parent / "does-not-exist.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{absent.as_posix()}")
    output = StringIO()
    assert await run_audit(output) == 2
    assert not absent.exists()


async def test_audit_pages_documents_and_receipt_references_without_rereading_files(
    restored_records,
    stored_document,
    monkeypatch,
):
    data = restored_records
    async with data["sessions"].begin() as db:
        docs = [stored_document(data["filing"].id, title=f"Attachment {i}") for i in range(260)]
        db.add_all(docs)
        await db.flush()
        for i in range(26):
            db.add(
                FilingTransaction(
                    filing_id=data["filing"].id,
                    submission_number=i + 2,
                    event_type="submitted",
                    actor_id=data["filing"].filer_id,
                    actor_name="Private filer",
                    occurred_at=datetime.now(UTC),
                    details={
                        "documents": [
                            {
                                "id": doc.id,
                                "sha256_hash": doc.sha256_hash,
                                "file_size_bytes": doc.file_size_bytes,
                            }
                            for doc in docs[i * 10 : (i + 1) * 10]
                        ]
                    },
                )
            )
    reads = []
    original = document_service.stored_integrity

    def counted(key):
        reads.append(key)
        return original(key)

    monkeypatch.setattr(document_service, "stored_integrity", counted)
    output = StringIO()
    assert await run_audit(output, court_id=data["filing"].court_id) == 0
    report = [json.loads(line) for line in output.getvalue().splitlines()]
    assert report[-1]["checked"] == {
        "document": 263,
        "public_copy": 2,
        "receipt_document": 263,
        "receipt_public_copy": 1,
    }
    assert len(reads) == len(set(reads)) == 265


@pytest.mark.parametrize("details", [{}, {"documents": []}, {"documents": [{"id": True}]}])
async def test_missing_or_malformed_manifests_are_not_silently_skipped(restored_records, details):
    data = restored_records
    async with data["sessions"].begin() as db:
        db.add(
            FilingTransaction(
                filing_id=data["filing"].id,
                submission_number=2,
                event_type="submitted",
                actor_id=data["filing"].filer_id,
                actor_name="Private filer",
                occurred_at=datetime.now(UTC),
                details=details,
            )
        )
    output = StringIO()
    assert await run_audit(output) == 1
    assert json.loads(output.getvalue().splitlines()[-1])["results"]["invalid_manifest"] == 1


def test_cli_preserves_existing_report(tmp_path):
    report = tmp_path / "existing.jsonl"
    report.write_text("Earlier recovery evidence", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "app.storage_audit", "--output", str(report)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 2
    assert "FileExistsError" in result.stderr
    assert report.read_text(encoding="utf-8") == "Earlier recovery evidence"


@pytest.mark.parametrize("missing_storage", [False, True])
async def test_cli_uses_configured_local_storage_without_creating_missing_directories(
    restored_records,
    missing_storage,
):
    data = restored_records
    storage = data["storage"] / "absent-storage" if missing_storage else data["storage"]
    result = subprocess.run(
        [sys.executable, "-m", "app.storage_audit"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=15,
        env={**os.environ, "DATABASE_URL": data["url"], "LOCAL_STORAGE_PATH": str(storage)},
    )
    assert result.returncode == int(missing_storage), result.stderr
    summary = json.loads(result.stdout.splitlines()[-1])
    assert summary["complete"]
    assert summary["results"]["missing" if missing_storage else "verified"] == 5
    if missing_storage:
        assert not storage.exists()


async def test_audit_keeps_one_database_snapshot_during_storage_reads(
    restored_records, monkeypatch
):
    data = restored_records
    async with data["sessions"]() as db:
        await db.execute(text("PRAGMA journal_mode=WAL"))
    started, release = threading.Event(), threading.Event()
    original = document_service.stored_integrity

    def paused_read(key):
        started.set()
        assert release.wait(10), "Test did not release the storage read"
        return original(key)

    monkeypatch.setattr(document_service, "stored_integrity", paused_read)
    output = StringIO()
    pending = asyncio.create_task(run_audit(output))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        async with data["sessions"].begin() as db:
            old = await db.get(FilingDocument, data["old"].id)
            old.sha256_hash = "0" * 64
    finally:
        release.set()
        result = await pending
    # The original snapshot is consistent. A second audit sees the later change.
    assert result == 0
    later = StringIO()
    assert await run_audit(later) == 1
    assert json.loads(later.getvalue().splitlines()[-1])["results"]["receipt_mismatch"] == 1
