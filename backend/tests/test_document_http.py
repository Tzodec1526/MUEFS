"""Exercise upload limits, stored bytes, and correction workflows through the API."""

import asyncio
import hashlib
import threading
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.auth import get_optional_user_id, require_user_may_manage_efilings
from app.config import settings
from app.database import get_db
from app.main import app
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.services import document_service
from tests.filing_requests import submission_review
from tests.test_filings import create_test_fixtures


@pytest.fixture
async def filing_client(db_session, monkeypatch, tmp_path):
    user, court, case_type = await create_test_fixtures(db_session)
    case_type.filing_fee_cents = 0
    envelope = FilingEnvelope(
        court_id=court.id, case_type_id=case_type.id, filer_id=user.id,
        case_title="A v B", filing_type="initial",
    )
    db_session.add(envelope)
    await db_session.flush()
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    monkeypatch.setattr(settings, "max_file_size_mb", 1)

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_user_may_manage_efilings] = lambda: user
    app.dependency_overrides[get_optional_user_id] = lambda: user.id
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, envelope, tmp_path
    finally:
        app.dependency_overrides.clear()


async def test_upload_size_limit_and_stored_document_integrity(filing_client, db_session):
    client, envelope, storage = filing_client
    payload = b"a" * (1024 * 1024)
    url = f"/api/v1/filings/{envelope.id}/documents"
    fields = {"title": "Record", "document_type_code": "COMPLAINT"}
    rejected = await client.post(url, headers={"Idempotency-Key": str(uuid4())}, data=fields,
                                 files={"file": ("record.txt", payload + b"x", "text/plain")})
    assert rejected.status_code == 413
    assert not list(storage.rglob("*.txt"))

    uploaded = await client.post(url, headers={"Idempotency-Key": str(uuid4())}, data=fields,
                                 files={"file": ("record.txt", payload, "text/plain")})
    assert uploaded.status_code == 200, uploaded.text
    document = uploaded.json()
    assert document["sha256_hash"] == hashlib.sha256(payload).hexdigest()
    downloaded = await client.get(f"/api/v1/documents/{document['id']}/download")
    assert downloaded.content == payload
    verified = await client.get(f"/api/v1/documents/{document['id']}/verify")
    assert verified.json()["is_valid"] is True
    stored = await db_session.scalar(
        select(FilingDocument).where(FilingDocument.id == document["id"])
    )
    (storage / stored.file_key).write_bytes(b"tampered")
    verified = await client.get(f"/api/v1/documents/{document['id']}/verify")
    assert verified.json()["is_valid"] is False


async def test_pdf_processing_does_not_block_unrelated_requests(filing_client, monkeypatch):
    client, envelope, _ = filing_client
    started, release = threading.Event(), threading.Event()

    def inspect(_data):
        started.set()
        assert release.wait(3), "PDF inspection blocked the request event loop"
        return document_service.PdfInspection(page_count=1)

    monkeypatch.setattr(document_service, "inspect_pdf", inspect)
    monkeypatch.setattr(document_service, "resolve_upload_mime_type", lambda *_: "application/pdf")
    upload = asyncio.create_task(client.post(
        f"/api/v1/filings/{envelope.id}/documents",
        headers={"Idempotency-Key": str(uuid4())},
        data={"title": "Record", "document_type_code": "COMPLAINT"},
        files={"file": ("record.pdf", b"%PDF-1.7\n", "application/pdf")},
    ))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        response = await asyncio.wait_for(client.get("/health"), timeout=1)
        assert response.status_code == 200
        assert not upload.done(), "Expected the upload to still be inspecting its PDF"
    finally:
        release.set()
        response = await upload
    assert response.status_code == 200


async def test_returned_filing_can_be_corrected_and_resubmitted(filing_client, db_session):
    client, envelope, _ = filing_client
    client.headers["X-Demo-User-Id"] = str(envelope.filer_id)
    envelope.status = FilingStatus.RETURNED
    envelope.rejection_reason = "Correct the description"
    envelope.reviewer_id = envelope.filer_id
    envelope.reviewed_at = datetime.now(UTC)
    await db_session.flush()
    original_id = envelope.id
    updated = await client.patch(f"/api/v1/filings/{original_id}",
                                 json={"expected_details_token": envelope.details_token,
                                       "filing_description": "Corrected description"})
    assert updated.status_code == 200, updated.text
    uploaded = await client.post(
        f"/api/v1/filings/{original_id}/documents",
        headers={"Idempotency-Key": str(uuid4())},
        data={"title": "Corrected complaint", "document_type_code": "COMPLAINT"},
        files={"file": ("complaint.txt", b"Corrected complaint", "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text
    # Production requests get a fresh session; discard this test session's cached list.
    db_session.expire(envelope, ["documents"])
    submitted = await client.post(
        f"/api/v1/filings/{original_id}/submit",
        json=await submission_review(client, original_id),
    )
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()
    assert result["id"] == original_id
    assert result["status"] == "submitted"
    assert result["filing_description"] == "Corrected description"
    assert result["documents"][0]["id"] == uploaded.json()["id"]
    assert result["reviewer_id"] is None
    assert result["reviewed_at"] is None
    assert result["rejection_reason"] is None
    second_submit = await client.post(
        f"/api/v1/filings/{original_id}/submit",
        json=await submission_review(client, original_id),
    )
    assert second_submit.status_code == 400
    edit_submitted = await client.patch(
        f"/api/v1/filings/{original_id}",
        json={"expected_details_token": envelope.details_token, "case_title": "Edit"},
    )
    assert edit_submitted.status_code == 400
