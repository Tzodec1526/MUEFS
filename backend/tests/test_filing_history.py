"""Exercise retained receipts through submission, correction, and clerk acceptance."""

import hashlib
from io import BytesIO
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.models.case import Case
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.notification import Notification
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import document_service, filing_service


async def filing_fixture(db):
    filer = User(
        email="receipt@test.com",
        first_name="Receipt",
        last_name="Filer",
        user_type=UserType.ATTORNEY,
    )
    clerk = User(
        email="records@test.com", first_name="Records", last_name="Clerk", user_type=UserType.CLERK
    )
    other = User(
        email="other@test.com", first_name="Other", last_name="Filer", user_type=UserType.ATTORNEY
    )
    court = Court(name="Records Court", county="Wayne", court_type=CourtType.CIRCUIT)
    db.add_all([filer, clerk, other, court])
    await db.flush()
    case_type = CaseType(
        court_id=court.id,
        name="No-fee matter",
        code="FREE",
        category=CaseCategory.CIVIL,
        filing_fee_cents=0,
    )
    db.add(case_type)
    db.add(UserCourtRole(user_id=clerk.id, court_id=court.id, role=CourtRole.CLERK))
    await db.flush()
    filing = FilingEnvelope(
        court_id=court.id,
        case_type_id=case_type.id,
        filer_id=filer.id,
        case_title="Original title",
        filing_type="initial",
    )
    db.add(filing)
    await db.flush()
    return filing.id, filer.id, clerk.id, other.id


@pytest_asyncio.fixture
async def record_filing(db_session, api_client, monkeypatch):
    ids = await filing_fixture(db_session)
    stored = {}
    monkeypatch.setattr(
        document_service, "upload_document", lambda data, key, mime: stored.__setitem__(key, data)
    )
    monkeypatch.setattr(document_service, "download_document", lambda key: BytesIO(stored[key]))
    monkeypatch.setattr(document_service, "delete_document", lambda key: stored.pop(key))
    api_client.headers["X-Demo-User-Id"] = str(ids[1])
    return ids


async def upload(client, fid, content):
    response = await client.post(
        f"/api/v1/filings/{fid}/documents",
        files={"file": ("filing.txt", content, "text/plain")},
        data={"title": "Complaint", "document_type_code": "COMPLAINT"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def test_receipts_keep_original_documents_through_correction(
    db_session,
    api_client,
    record_filing,
):
    fid, filer, clerk, other = record_filing
    original = await upload(api_client, fid, b"Original complaint")
    key = {"Idempotency-Key": str(uuid4())}
    first = await api_client.post(f"/api/v1/filings/{fid}/submit", headers=key)
    assert first.status_code == 200, first.text
    replay = await api_client.post(f"/api/v1/filings/{fid}/submit", headers=key)
    assert replay.status_code == 200
    assert replay.json()["submission_count"] == 1
    first_receipt = (await api_client.get(f"/api/v1/filings/{fid}/history")).json()["transactions"][
        0
    ]
    assert (
        first_receipt["details"]["documents"][0]["sha256_hash"]
        == hashlib.sha256(b"Original complaint").hexdigest()
    )

    assert first_receipt["occurred_at"].endswith("+00:00")
    assert first_receipt["details"]["documents"][0]["uploaded_at"].endswith("+00:00")

    api_client.headers["X-Demo-User-Id"] = str(clerk)
    blank = await api_client.post(
        f"/api/v1/clerk/filings/{fid}/review", json={"action": "return", "reason": "   "}
    )
    assert blank.status_code == 400
    returned = await api_client.post(
        f"/api/v1/clerk/filings/{fid}/review",
        json={"action": "return", "reason": "Correct the caption"},
    )
    assert returned.status_code == 200
    api_client.headers["X-Demo-User-Id"] = str(filer)
    assert (
        await api_client.delete(f"/api/v1/filings/{fid}/documents/{original}")
    ).status_code == 204
    assert (
        await api_client.get(f"/api/v1/documents/{original}/download")
    ).content == b"Original complaint"
    await api_client.patch(f"/api/v1/filings/{fid}", json={"case_title": "Corrected title"})
    corrected = await upload(api_client, fid, b"Corrected complaint")
    submitted = await api_client.post(
        f"/api/v1/filings/{fid}/submit", headers={"Idempotency-Key": str(uuid4())}
    )
    assert submitted.json()["submission_count"] == 2
    assert [d["id"] for d in submitted.json()["documents"]] == [corrected]
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    accepted = await api_client.post(
        f"/api/v1/clerk/filings/{fid}/review", json={"action": "accept"}
    )
    assert accepted.status_code == 200, accepted.text
    case_id = accepted.json()["case_id"]
    history = (await api_client.get(f"/api/v1/filings/{fid}/history")).json()
    assert [t["event_type"] for t in history["transactions"]] == [
        "accepted",
        "submitted",
        "returned",
        "submitted",
    ]
    assert history["transactions"][-1] == first_receipt
    assert history["transactions"][1]["details"]["case_title"] == "Corrected title"
    assert history["transactions"][-1]["details"]["case_title"] == "Original title"
    assert history["transactions"][-1]["occurred_at"] != history["transactions"][1]["occurred_at"]
    assert await db_session.scalar(select(func.count()).select_from(Notification)) == 4
    assert await db_session.get(FilingDocument, original) is not None

    api_client.headers["X-Demo-User-Id"] = str(other)
    assert (await api_client.get(f"/api/v1/filings/{fid}/history")).status_code == 403
    assert (await api_client.get(f"/api/v1/documents/{original}/download")).status_code == 403
    assert (await api_client.get(f"/api/v1/documents/{corrected}/download")).status_code == 200
    public = (await api_client.get(f"/api/v1/cases/{case_id}/filings")).json()
    assert [d["id"] for d in public[0]["documents"]] == [corrected]
    api_client.headers["X-Demo-User-Id"] = str(filer)
    page = (await api_client.get(f"/api/v1/filings/{fid}/history?page_size=2&page=2")).json()
    assert page["total"] == 4
    assert page["transactions"][-1] == first_receipt


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE filing_transactions SET actor_name = 'Tampered'",
        "DELETE FROM filing_transactions",
    ],
)
async def test_transaction_retention_blocks_direct_sql(
    db_session, api_client, record_filing, statement
):
    fid = record_filing[0]
    await upload(api_client, fid, b"Complaint")
    await api_client.post(f"/api/v1/filings/{fid}/submit")
    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(text(statement))
    assert await db_session.scalar(select(func.count()).select_from(FilingTransaction)) == 1


async def test_failed_batch_item_rolls_back_its_records_only(
    db_session,
    api_client,
    record_filing,
    monkeypatch,
):
    fid, filer, clerk, _other = record_filing
    await upload(api_client, fid, b"Complaint")
    await api_client.post(f"/api/v1/filings/{fid}/submit")
    original = await db_session.get(FilingEnvelope, fid)
    second = FilingEnvelope(
        court_id=original.court_id,
        case_type_id=original.case_type_id,
        filer_id=filer,
        case_title="Second",
        status=FilingStatus.SUBMITTED,
    )
    db_session.add(second)
    await db_session.flush()
    second_id = second.id
    real_review = filing_service.review_filing

    async def interrupted_review(db, filing_id, **kwargs):
        result = await real_review(db, filing_id, **kwargs)
        if filing_id == fid:
            raise RuntimeError("Failure after acceptance writes")
        return result

    monkeypatch.setattr(filing_service, "review_filing", interrupted_review)
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    batch = await api_client.post(
        "/api/v1/clerk/queue/batch-review",
        json={
            "action": "accept",
            "filing_ids": [fid, second_id, second_id],
        },
    )
    assert batch.status_code == 200, batch.text
    assert batch.json() == {"succeeded": [second_id], "failed": [fid]}
    first = await filing_service.get_filing(db_session, fid)
    assert first.status == FilingStatus.SUBMITTED
    assert first.case_id is None
    assert await db_session.scalar(select(func.count()).select_from(Case)) == 1
    assert await db_session.scalar(select(func.count()).select_from(FilingTransaction)) == 2
    assert await db_session.scalar(select(func.count()).select_from(Notification)) == 2


@pytest.mark.parametrize("sealed", [False, True])
async def test_case_standing_does_not_expose_private_filing_material(
    db_session,
    api_client,
    record_filing,
    sealed,
):
    from datetime import UTC, datetime

    from app.models.case import CaseParticipant, ParticipantRole

    fid, filer, _clerk, other = record_filing
    filing = await db_session.get(FilingEnvelope, fid)
    case = Case(
        court_id=filing.court_id,
        case_type_id=filing.case_type_id,
        case_number="PRIVACY",
        title="Case",
        filed_date=datetime.now(UTC),
        is_sealed=sealed,
    )
    db_session.add(case)
    await db_session.flush()
    doc_id = await upload(api_client, fid, b"Private financial information")
    doc = await db_session.get(FilingDocument, doc_id)
    doc.is_confidential = True
    doc.title = "Confidential exhibit title"
    filing.case_id = case.id
    filing.status = FilingStatus.ACCEPTED
    filing.fee_waiver_reason = "Private financial hardship"
    db_session.add(
        CaseParticipant(
            case_id=case.id, user_id=other, party_name="Other party", role=ParticipantRole.DEFENDANT
        )
    )
    draft = FilingEnvelope(
        court_id=filing.court_id,
        case_type_id=filing.case_type_id,
        case_id=case.id,
        filer_id=filer,
        case_title="Private unsubmitted draft",
    )
    db_session.add(draft)
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(other)
    response = await api_client.get(f"/api/v1/cases/{case.id}/filings")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [fid]
    assert response.json()[0]["documents"] == []
    assert "fee_waiver_reason" not in response.text
    assert "Confidential exhibit title" not in response.text
    assert "Private" not in response.text
    assert (await api_client.get(f"/api/v1/filings/{fid}")).status_code == 403
    assert (await api_client.get(f"/api/v1/documents/{doc_id}/download")).status_code == 403
    api_client.headers["X-Demo-User-Id"] = str(filer)
    assert (await api_client.get(f"/api/v1/filings/{fid}")).json()["fee_waiver_reason"] == (
        "Private financial hardship"
    )


async def test_fee_waiver_document_is_nonpublic_without_checkbox(
    db_session,
    api_client,
    record_filing,
):
    fid = record_filing[0]
    response = await api_client.post(
        f"/api/v1/filings/{fid}/documents",
        files={"file": ("waiver.txt", b"Financial hardship", "text/plain")},
        data={
            "title": "Fee waiver request",
            "document_type_code": "FEE_WAIVER",
            "is_confidential": "false",
        },
    )
    assert response.status_code == 200
    doc = await db_session.get(FilingDocument, response.json()["id"])
    assert doc.is_confidential is True
