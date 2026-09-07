"""Receipts and acceptance require the stored attachment bytes, not just database rows."""

import asyncio
import hashlib
import threading
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.services import document_service, filing_service
from tests.filing_requests import submission_review
from tests.test_document_publication import publication_pdf
from tests.test_filing_history import filing_fixture


@pytest.fixture
async def stored_filing(db_session, api_client, tmp_path, monkeypatch):
    fid, filer, clerk, _ = await filing_fixture(db_session)
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    api_client.headers["X-Demo-User-Id"] = str(filer)
    documents = []
    for name, content, mime in [
        ("Pleading.txt", b"Original pleading", "text/plain"),
        ("Exhibit.pdf", publication_pdf("Sensitive number 123-45-6789"), "application/pdf"),
    ]:
        response = await api_client.post(
            f"/api/v1/filings/{fid}/documents",
            headers={"Idempotency-Key": str(uuid4())},
            data={"title": name, "document_type_code": "EXHIBIT"},
            files={"file": (name, content, mime)},
        )
        assert response.status_code == 200, response.text
        doc = await db_session.get(FilingDocument, response.json()["id"])
        documents.append((doc, content))
    return fid, filer, clerk, documents, tmp_path


@pytest.mark.parametrize("action", ["submit", "accept"])
@pytest.mark.parametrize("damage", ["missing", "changed", "wrong_size", "storage_outage"])
async def test_missing_or_changed_bytes_cannot_be_submitted_or_accepted(
    stored_filing,
    api_client,
    db_session,
    monkeypatch,
    action,
    damage,
):
    fid, _, clerk, documents, storage = stored_filing
    if action == "accept":
        assert (await api_client.post(
            f"/api/v1/filings/{fid}/submit",
            json=await submission_review(api_client, fid),
        )).status_code == 200
        api_client.headers["X-Demo-User-Id"] = str(clerk)
    doc, content = documents[0]
    path = storage / doc.file_key
    download = document_service.download_document
    if damage == "missing":
        path.unlink()
    elif damage == "changed":
        path.write_bytes(b"X" + content[1:])  # Same length: a size-only check cannot detect this.
    elif damage == "wrong_size":
        doc.file_size_bytes += 1
        await db_session.flush()
    else:
        from botocore.exceptions import EndpointConnectionError

        def unavailable(*args):
            raise EndpointConnectionError(endpoint_url="http://local-storage.test")

        monkeypatch.setattr(document_service, "download_document", unavailable)
    prior_count = await db_session.scalar(select(func.count()).select_from(FilingTransaction))

    async def unexpected_cms(*args):
        pytest.fail("An unverifiable filing reached the CMS")

    monkeypatch.setattr(filing_service, "submit_filing_to_cms", unexpected_cms)
    response = await api_client.post(
        f"/api/v1/filings/{fid}/submit"
        if action == "submit"
        else f"/api/v1/clerk/filings/{fid}/review",
        **(
            {"json": {"action": "accept", "expected_submission_count": 1}}
            if action == "accept"
            else {"json": await submission_review(api_client, fid)}
        ),
    )
    assert response.status_code == 409
    assert doc.title in response.json()["detail"]
    filing = await db_session.get(FilingEnvelope, fid)
    assert filing.status == (FilingStatus.DRAFT if action == "submit" else FilingStatus.SUBMITTED)
    assert filing.reviewed_at is None and filing.reviewer_id is None
    assert (
        await db_session.scalar(select(func.count()).select_from(FilingTransaction)) == prior_count
    )
    # Restoring the exact stored file permits submission; acceptance still needs its CMS.
    path.write_bytes(content)
    doc.file_size_bytes = len(content)
    await db_session.flush()
    monkeypatch.setattr(document_service, "download_document", download)
    if action == "submit":
        assert (await api_client.post(
            f"/api/v1/filings/{fid}/submit",
            json=await submission_review(api_client, fid),
        )).status_code == 200


async def test_validation_reuses_upload_screening_without_reading_storage(
    stored_filing,
    api_client,
    monkeypatch,
    db_session,
):
    fid, _, _, documents, _ = stored_filing

    def unexpected_read(*args):
        pytest.fail("Advisory validation reread stored document bytes")

    monkeypatch.setattr(document_service, "download_document", unexpected_read)
    for _ in range(2):
        response = await api_client.post(f"/api/v1/filings/{fid}/validate")
        assert response.status_code == 200 and response.json()["is_valid"]
        assert any("Social Security" in warning for warning in response.json()["warnings"])
    pdf = documents[1][0]
    pdf.pii_warnings = None
    await db_session.flush()
    response = await api_client.post(f"/api/v1/filings/{fid}/validate")
    assert any(
        "no retained PII screening result" in warning for warning in response.json()["warnings"]
    )


async def test_integrity_streams_in_chunks_and_keeps_the_event_loop_available(
    stored_filing,
    api_client,
    monkeypatch,
):
    fid, _, _, _, _ = stored_filing
    started, release = threading.Event(), threading.Event()
    download = document_service.download_document
    reads = []

    class SlowStream:
        def __init__(self, file_key):
            self.stream = download(file_key)

        def read(self, size):
            reads.append(size)
            started.set()
            assert release.wait(5), "The event loop was blocked by storage verification"
            return self.stream.read(size)

        def close(self):
            self.stream.close()

    monkeypatch.setattr(document_service, "download_document", SlowStream)
    submit = asyncio.create_task(api_client.post(
        f"/api/v1/filings/{fid}/submit",
        json=await submission_review(api_client, fid),
    ))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        assert (await asyncio.wait_for(api_client.get("/health"), 2)).status_code == 200
        assert not submit.done()
    finally:
        release.set()
        response = await submit
    assert response.status_code == 200
    assert reads and all(size == 64 * 1024 for size in reads)


async def test_submission_retry_replays_receipt_without_new_file_work(
    stored_filing,
    api_client,
    monkeypatch,
    db_session,
):
    fid, _, _, documents, _ = stored_filing
    key = {"Idempotency-Key": str(uuid4())}
    first = await api_client.post(
        f"/api/v1/filings/{fid}/submit",
        json=await submission_review(api_client, fid),
        headers=key,
    )
    assert first.status_code == 200

    def unexpected_read(*args):
        pytest.fail("An already completed submission was verified and recorded again")

    monkeypatch.setattr(document_service, "stored_integrity", unexpected_read)
    assert (await api_client.post(
        f"/api/v1/filings/{fid}/submit",
        json=await submission_review(api_client, fid),
        headers=key,
    )).status_code == 200
    transactions = list(await db_session.scalars(select(FilingTransaction)))
    assert len(transactions) == 1
    assert (
        transactions[0].details["documents"][0]["sha256_hash"]
        == hashlib.sha256(documents[0][1]).hexdigest()
    )


async def test_unreadable_pdf_is_rejected_before_it_becomes_an_attachment(
    stored_filing, api_client, db_session
):
    fid, _, _, _, _ = stored_filing
    count = await db_session.scalar(select(func.count()).select_from(FilingDocument))
    response = await api_client.post(
        f"/api/v1/filings/{fid}/documents",
        headers={"Idempotency-Key": str(uuid4())},
        data={"title": "Broken", "document_type_code": "EXHIBIT"},
        files={"file": ("broken.pdf", b"%PDF-1.7\nnot a PDF", "application/pdf")},
    )
    assert response.status_code == 422
    assert await db_session.scalar(select(func.count()).select_from(FilingDocument)) == count


async def test_batch_acceptance_preserves_healthy_filing_when_another_file_is_missing(
    stored_filing,
    stored_document,
    api_client,
    db_session,
):
    fid, filer, clerk, documents, storage = stored_filing
    assert (await api_client.post(
        f"/api/v1/filings/{fid}/submit",
        json=await submission_review(api_client, fid),
    )).status_code == 200
    source = await db_session.get(FilingEnvelope, fid)
    second = FilingEnvelope(
        court_id=source.court_id,
        case_type_id=source.case_type_id,
        filer_id=filer,
        case_title="Healthy filing",
        filing_type="initial",
    )
    db_session.add(second)
    await db_session.flush()
    db_session.add(stored_document(second.id))
    await db_session.flush()
    assert (await api_client.post(
        f"/api/v1/filings/{second.id}/submit",
        json=await submission_review(api_client, second.id),
    )).status_code == 200
    (storage / documents[0][0].file_key).unlink()
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    response = await api_client.post(
        "/api/v1/clerk/queue/batch-review",
        json={
            "action": "accept",
            "filings": [
                {"filing_id": target_id, "expected_submission_count": 1}
                for target_id in [second.id, fid]
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["succeeded"] == [second.id]
    assert response.json()["failed"] == [fid]
    assert set(response.json()["errors"]) == {str(fid)}
    assert "unavailable" in response.json()["errors"][str(fid)]
    first = await filing_service.get_filing(db_session, fid)
    assert first.status == FilingStatus.SUBMITTED and first.reviewer_id is None
    assert (await db_session.get(FilingEnvelope, second.id)).status == FilingStatus.ACCEPTED
