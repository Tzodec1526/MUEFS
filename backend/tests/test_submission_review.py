"""A submission must match the filing the filer reviewed."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models.filing_transaction import FilingTransaction
from app.models.notification import Notification
from tests.filing_requests import submission_review
from tests.test_filing_history import record_filing as record_filing
from tests.test_filing_history import upload


@pytest.mark.parametrize(
    "review", [{}, {"expected_submission_token": "not-a-reviewed-token"}],
    ids=["missing_token", "malformed_token"],
)
async def test_submission_requires_a_reviewed_version(api_client, record_filing, review):
    fid, *_ = record_filing
    await upload(api_client, fid, b"Complaint for review")
    # With a JSON body, validation reaches the token field; a bodiless request fails earlier.
    response = await api_client.post(f"/api/v1/filings/{fid}/submit", json=review)
    assert response.status_code == 422, response.text
    locations = [error["loc"] for error in response.json()["detail"]]
    assert locations == [["body", "expected_submission_token"]]
    filing = (await api_client.get(f"/api/v1/filings/{fid}")).json()
    assert filing["status"] == "draft"
    assert filing["submission_count"] == 0


@pytest.mark.parametrize("change", ["details", "add_document", "remove_document", "waiver"])
async def test_changed_review_cannot_create_a_receipt(
    api_client, db_session, record_filing, change,
):
    fid, *_ = record_filing
    first = await upload(api_client, fid, b"Complaint")
    await upload(api_client, fid, b"Exhibit")
    if change == "waiver":
        attached = await api_client.post(
            f"/api/v1/filings/{fid}/documents",
            headers={"Idempotency-Key": str(uuid4())},
            files={"file": ("waiver.txt", b"Signed synthetic waiver request", "text/plain")},
            data={"title": "Waiver", "document_type_code": "FEE_WAIVER"},
        )
        assert attached.status_code == 200, attached.text
    opened = (await api_client.get(f"/api/v1/filings/{fid}")).json()
    review = {"expected_submission_token": opened["submission_token"]}
    if change == "details":
        response = await api_client.patch(f"/api/v1/filings/{fid}", json={
            "expected_details_token": opened["details_token"],
            "case_title": "Caption corrected in another tab",
            "filing_description": "Updated description",
        })
        assert response.status_code == 200, response.text
    elif change == "add_document":
        await upload(api_client, fid, b"Unreviewed attachment")
    elif change == "remove_document":
        response = await api_client.delete(f"/api/v1/filings/{fid}/documents/{first}")
        assert response.status_code == 204, response.text
    else:
        response = await api_client.patch(
            f"/api/v1/filings/{fid}", json={
                "expected_details_token": opened["details_token"],
                "fee_waiver_requested": True,
            },
        )
        assert response.status_code == 200, response.text

    response = await api_client.post(f"/api/v1/filings/{fid}/submit", json=review)
    assert response.status_code == 409, response.text
    assert "Refresh the review" in response.json()["detail"]
    assert await db_session.scalar(select(func.count()).select_from(FilingTransaction)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Notification)) == 0
    saved = (await api_client.get(f"/api/v1/filings/{fid}")).json()
    assert saved["status"] == "draft" and saved["submission_count"] == 0
    assert saved["submission_token"] != opened["submission_token"]
    submitted = await api_client.post(
        f"/api/v1/filings/{fid}/submit",
        json=await submission_review(api_client, fid),
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["submission_count"] == 1


async def test_retry_recovers_receipt_but_old_review_cannot_resubmit_returned_filing(
    api_client, db_session, record_filing,
):
    fid, filer, clerk, other = record_filing
    await upload(api_client, fid, b"Reviewed complaint")
    review = await submission_review(api_client, fid)
    key = {"Idempotency-Key": str(uuid4())}
    submitted = await api_client.post(f"/api/v1/filings/{fid}/submit", json=review, headers=key)
    assert submitted.status_code == 200, submitted.text
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    returned = await api_client.post(f"/api/v1/clerk/filings/{fid}/review", json={
        "action": "return", "reason": "Correct the caption", "expected_submission_count": 1,
    })
    assert returned.status_code == 200, returned.text
    api_client.headers["X-Demo-User-Id"] = str(other)
    denied = await api_client.post(f"/api/v1/filings/{fid}/submit", json=review, headers=key)
    assert denied.status_code == 403
    api_client.headers["X-Demo-User-Id"] = str(filer)
    replay = await api_client.post(f"/api/v1/filings/{fid}/submit", json=review, headers=key)
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "returned" and replay.json()["submission_count"] == 1
    stale = await api_client.post(f"/api/v1/filings/{fid}/submit", json=review,
                                  headers={"Idempotency-Key": str(uuid4())})
    assert stale.status_code == 409, stale.text
    assert await db_session.scalar(select(func.count()).select_from(FilingTransaction)) == 2
    assert await db_session.scalar(select(func.count()).select_from(Notification)) == 2
    resubmitted = await api_client.post(
        f"/api/v1/filings/{fid}/submit",
        json=await submission_review(api_client, fid),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert resubmitted.status_code == 200, resubmitted.text
    assert resubmitted.json()["submission_count"] == 2


async def test_an_unknown_review_action_is_an_invalid_request(api_client, record_filing):
    fid, _filer, clerk, _other = record_filing
    await upload(api_client, fid, b"Complaint awaiting review")
    submitted = await api_client.post(
        f"/api/v1/filings/{fid}/submit", json=await submission_review(api_client, fid),
    )
    assert submitted.status_code == 200, submitted.text
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    single = await api_client.post(f"/api/v1/clerk/filings/{fid}/review", json={
        "action": "approve", "expected_submission_count": 1,
    })
    batch = await api_client.post("/api/v1/clerk/queue/batch-review", json={
        "action": "reject", "filings": [{"filing_id": fid, "expected_submission_count": 1}],
    })
    for response in (single, batch):
        assert response.status_code == 422, response.text
        assert [error["loc"] for error in response.json()["detail"]] == [["body", "action"]]
    filing = (await api_client.get(f"/api/v1/filings/{fid}")).json()
    assert filing["status"] == "submitted" and filing["reviewed_at"] is None
