"""An upload retry must preserve one stored document and one fee-state change."""

from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.auth import get_current_user, require_user_may_manage_efilings
from app.main import app
from app.models.audit import AuditLog
from app.models.filing import DocumentUploadRequest, FilingDocument, FilingEnvelope, FilingStatus
from app.models.storage_deletion import StorageDeletion
from app.models.user import User
from app.services import document_service
from app.storage_cleanup import cleanup_next
from tests.test_document_http import filing_client as filing_client
from tests.test_malware_scan import scanner as scanner


async def test_lost_upload_response_can_retry_without_duplicate_document(
    filing_client, db_session, scanner, monkeypatch,
):
    client, filing, storage = filing_client
    writes = Mock(wraps=document_service.upload_document)
    monkeypatch.setattr(document_service, "upload_document", writes)
    headers = {"Idempotency-Key": str(uuid4())}
    data = {"title": "Complaint", "document_type_code": "COMPLAINT"}
    file = {"file": ("complaint.txt", b"Synthetic upload recovery document", "text/plain")}
    url = f"/api/v1/filings/{filing.id}/documents"
    first = await client.post(url, headers=headers, data=data, files=file)
    assert first.status_code == 200, first.text
    version = filing.fee_version
    scanner["reply"] = None  # A recorded success remains recoverable during a scanner outage.
    retry = await client.post(url, headers=headers, data=data, files=file)
    assert retry.status_code == 200, retry.text
    assert retry.json() == first.json()
    assert filing.fee_version == version
    assert len(list(storage.rglob("*.txt"))) == 1
    assert len(scanner["received"]) == 1
    assert writes.call_count == 1
    assert await db_session.scalar(select(func.count()).select_from(DocumentUploadRequest)) == 1
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.action == "upload_document",
    )) == 1


@pytest.mark.parametrize("change", ["content", "title", "type", "confidential", "name", "mime"])
async def test_request_key_cannot_be_reused_for_a_different_upload(filing_client, change):
    client, filing, storage = filing_client
    headers = {"Idempotency-Key": str(uuid4())}
    data = {"title": "Original", "document_type_code": "COMPLAINT", "is_confidential": "false"}
    content, name, mime = b"Original synthetic document", "record.txt", "text/plain"
    url = f"/api/v1/filings/{filing.id}/documents"
    first = await client.post(url, headers=headers, data=data,
                              files={"file": (name, content, mime)})
    assert first.status_code == 200, first.text
    version = filing.fee_version
    if change == "content":
        content = b"Different synthetic bytes"
    elif change == "title":
        data["title"] = "Changed title"
    elif change == "type":
        data["document_type_code"] = "EXHIBIT"
    elif change == "confidential":
        data["is_confidential"] = "true"
    elif change == "name":
        name = "different.txt"
    else:
        mime = "application/pdf"
    replay = await client.post(url, headers=headers, data=data,
                               files={"file": (name, content, mime)})
    assert replay.status_code == 409, replay.text
    assert filing.fee_version == version
    assert len(list(storage.rglob("*.txt"))) == 1


@pytest.mark.parametrize("key", [None, "not-a-uuid"])
async def test_upload_requires_a_valid_request_key(filing_client, key):
    client, filing, storage = filing_client
    response = await client.post(f"/api/v1/filings/{filing.id}/documents",
        headers={"Idempotency-Key": key} if key else {},
        data={"title": "Unkeyed", "document_type_code": "COMPLAINT"},
        files={"file": ("record.txt", b"Synthetic upload", "text/plain")})
    assert response.status_code == 422
    assert not list(storage.rglob("*.txt"))


@pytest.mark.parametrize("retained", [False, True])
async def test_retry_does_not_resurrect_a_removed_document(filing_client, db_session, retained):
    client, filing, storage = filing_client
    headers = {"Idempotency-Key": str(uuid4())}
    data = {"title": "Remove me", "document_type_code": "COMPLAINT"}
    file = {"file": ("record.txt", b"Synthetic removed document", "text/plain")}
    url = f"/api/v1/filings/{filing.id}/documents"
    first = await client.post(url, headers=headers, data=data, files=file)
    assert first.status_code == 200, first.text
    document_id = first.json()["id"]
    if retained:
        filing.status = FilingStatus.RETURNED
        filing.submitted_at = datetime.now(UTC)
        doc = await db_session.get(FilingDocument, document_id)
        doc.retained_at = datetime.now(UTC)
        await db_session.flush()
    removed = await client.delete(f"{url}/{document_id}")
    assert removed.status_code == 204, removed.text
    version = filing.fee_version
    replay = await client.post(url, headers=headers, data=data, files=file)
    assert replay.status_code == 409, replay.text
    assert "later removed" in replay.json()["detail"]
    assert filing.fee_version == version
    assert len(list(storage.rglob("*.txt"))) == 1  # Removal has not yet deleted storage.
    assert await db_session.scalar(select(func.count()).select_from(StorageDeletion)) == (
        0 if retained else 1
    )
    replacement = await client.post(url, headers={"Idempotency-Key": str(uuid4())},
                                    data=data, files=file)
    assert replacement.status_code == 200, replacement.text
    old_retry = await client.post(url, headers=headers, data=data, files=file)
    assert old_retry.status_code == 409, old_retry.text
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    assert await cleanup_next(sessions) == (None if retained else "deleted")
    assert len(list(storage.rglob("*.txt"))) == 1 + int(retained)
    async with sessions() as db:
        new_doc = await db.get(FilingDocument, replacement.json()["id"])
        assert document_service.stored_integrity(new_doc.file_key) == (
            new_doc.sha256_hash, new_doc.file_size_bytes,
        )


async def test_replay_after_submission_and_keys_are_scoped_to_the_filing(filing_client, db_session):
    client, filing, _storage = filing_client
    headers = {"Idempotency-Key": str(uuid4())}
    data = {"title": "Complaint", "document_type_code": "COMPLAINT"}
    file = {"file": ("record.txt", b"Synthetic submission", "text/plain")}
    url = f"/api/v1/filings/{filing.id}/documents"
    first = await client.post(url, headers=headers, data=data, files=file)
    assert first.status_code == 200, first.text
    filing.status = FilingStatus.SUBMITTED
    await db_session.flush()
    retry = await client.post(url, headers=headers, data=data, files=file)
    assert retry.status_code == 200 and retry.json() == first.json()
    assert filing.status == FilingStatus.SUBMITTED
    new = await client.post(url, headers={"Idempotency-Key": str(uuid4())}, data=data, files=file)
    assert new.status_code == 400
    other = FilingEnvelope(court_id=filing.court_id, case_type_id=filing.case_type_id,
                           filer_id=filing.filer_id, case_title="Separate filing",
                           filing_type="initial")
    db_session.add(other)
    await db_session.flush()
    distinct = await client.post(f"/api/v1/filings/{other.id}/documents",
                                 headers=headers, data=data, files=file)
    assert distinct.status_code == 200 and distinct.json()["id"] != first.json()["id"]
    # Replay still goes through the current account and filing-ownership checks.
    app.dependency_overrides.pop(require_user_may_manage_efilings, None)
    app.dependency_overrides.pop(get_current_user, None)
    user = await db_session.get(User, filing.filer_id)
    user.is_active = False
    await db_session.flush()
    denied = await client.post(url, headers={**headers, "X-Demo-User-Id": str(user.id)},
                               data=data, files=file)
    assert denied.status_code == 401, denied.text
