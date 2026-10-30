"""Court assessments, retained evidence, and balances exercised through the HTTP workflow."""

from copy import deepcopy
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.api.auth import get_current_user_id
from app.config import settings
from app.main import app
from app.models.court import CaseType
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.notification import Notification
from app.models.payment import Payment, PaymentStatus
from app.models.user import User, UserType
from app.services import audit_service, document_service, filing_service
from app.services.fee_assessment_service import fee_state
from tests.filing_requests import submission_review
from tests.test_fee_waivers import decision_pdf
from tests.test_filing_history import filing_fixture


def assessment(version, amount):
    return {
        "expected_version": version,
        "authority_reference": "Synthetic court-approved fee schedule, item 3",
        "reason": "Reviewed charges and exceptions for the attached documents",
        "items": [
            {
                "fee_type": "reviewed_fee",
                "description": "Court-assessed fee",
                "amount_cents": amount,
            }
        ],
        "reviewed": True,
    }


@pytest_asyncio.fixture
async def fee_filing(db_session, stored_document):
    fid, filer, clerk, other = await filing_fixture(db_session)
    filing = await db_session.get(FilingEnvelope, fid)
    case_type = await db_session.get(CaseType, filing.case_type_id)
    case_type.filing_fee_cents = 1000
    doc = stored_document(fid)
    db_session.add(doc)
    await db_session.flush()
    return fid, filer, clerk, other, doc


@pytest.mark.parametrize("total", [0, 750])
async def test_review_assessment_payment_and_submission_preserve_the_basis(
    db_session,
    api_client,
    fee_filing,
    total,
):
    fid, filer, clerk, other, doc = fee_filing
    api_client.headers["X-Demo-User-Id"] = str(filer)
    initial = (await api_client.get(f"/api/v1/filings/{fid}/fees")).json()
    assert initial["source"] == "demo" and initial["total_cents"] == 1000
    requested = await api_client.post(
        f"/api/v1/filings/{fid}/fee-review",
        json={
            "expected_version": initial["version"],
            "reason": "Please review the applicable exemption",
        },
    )
    assert requested.status_code == 201, requested.text
    pending = requested.json()
    assert pending["total_cents"] is None and pending["balance_due_cents"] is None
    assert pending["review_reason"] == "Please review the applicable exemption"
    assert pending["review_requested_at"].endswith("Z")
    filing = await filing_service.get_filing(db_session, fid)
    assert filing.status == FilingStatus.DRAFT and filing.submitted_at is None
    assert filing.submission_count == 0 and doc.retained_at is not None
    assert (await api_client.post(
        f"/api/v1/filings/{fid}/submit",
        json=await submission_review(api_client, fid),
    )).status_code == 402
    assert (
        await api_client.get(
            "/api/v1/clerk/fee-reviews",
            params={
                "court_id": filing.court_id,
            },
        )
    ).status_code == 403
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    queue = await api_client.get("/api/v1/clerk/fee-reviews", params={"court_id": filing.court_id})
    assert queue.json()["total"] == 1 and queue.json()["filings"][0]["id"] == fid
    assert queue.json()["filings"][0]["requested_at"].endswith("+00:00")
    approved = await api_client.post(
        f"/api/v1/clerk/filings/{fid}/fees",
        json=assessment(
            pending["version"],
            total,
        ),
    )
    assert approved.status_code == 201, approved.text
    fees = approved.json()
    assert fees["source"] == "court" and fees["total_cents"] == total
    assert fees["review_requested_at"] is None and fees["review_reason"] is None
    assert (
        await api_client.get(
            "/api/v1/clerk/fee-reviews",
            params={
                "court_id": filing.court_id,
            },
        )
    ).json()["total"] == 0
    assessed = await db_session.get(FilingTransaction, fees["assessment_id"])
    retained = deepcopy(assessed.details)
    assert retained["documents"][0]["sha256_hash"] == doc.sha256_hash
    api_client.headers["X-Demo-User-Id"] = str(other)
    assert (await api_client.get(f"/api/v1/filings/{fid}/fees")).status_code == 403
    api_client.headers["X-Demo-User-Id"] = str(filer)
    if total:
        assert (await api_client.post(
            f"/api/v1/filings/{fid}/submit",
            json=await submission_review(api_client, fid),
        )).status_code == 402
        payment = {
            "envelope_id": fid,
            "payment_method": "credit_card",
            "amount_cents": total,
            "expected_fee_version": fees["version"],
        }
        assert (
            await api_client.post(
                "/api/v1/payments/process",
                json={
                    **payment,
                    "amount_cents": total - 1,
                },
            )
        ).status_code == 400
        assert (
            await api_client.post(
                "/api/v1/payments/process",
                json={
                    **payment,
                    "expected_fee_version": pending["version"],
                },
            )
        ).status_code == 409
        paid = await api_client.post("/api/v1/payments/process", json=payment)
        assert paid.status_code == 201, paid.text
        assert paid.json()["is_simulated"] is True
        assert (await api_client.post("/api/v1/payments/process", json=payment)).status_code == 409
        record = await db_session.get(Payment, paid.json()["id"])
        assert record.envelope_id == fid and record.fee_basis["assessment_id"] == assessed.id
    submitted = await api_client.post(
        f"/api/v1/filings/{fid}/submit",
        json=await submission_review(api_client, fid),
    )
    assert submitted.status_code == 200, submitted.text
    receipt = (await api_client.get(f"/api/v1/filings/{fid}/history")).json()["transactions"][0]
    assert receipt["event_type"] == "submitted" and receipt["submission_number"] == 1
    assert receipt["details"]["fee_assessment"]["assessment_id"] == assessed.id
    assert receipt["details"]["fee_assessment"]["paid_cents"] == total
    assert receipt["details"]["fee_assessment"]["balance_due_cents"] == 0
    assert len(receipt["details"]["payments"]) == bool(total)
    await db_session.refresh(assessed)  # Compare the stored row, not the cached object.
    assert assessed.details == retained


async def test_changed_documents_require_reassessment_and_credit_prior_payments(
    db_session,
    api_client,
    fee_filing,
):
    fid, filer, clerk, _, doc = fee_filing
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    assessed = (
        await api_client.post(f"/api/v1/clerk/filings/{fid}/fees", json=assessment(0, 1000))
    ).json()
    first = await db_session.get(FilingTransaction, assessed["assessment_id"])
    first_details = deepcopy(first.details)
    api_client.headers["X-Demo-User-Id"] = str(filer)
    paid = await api_client.post(
        "/api/v1/payments/process",
        json={
            "envelope_id": fid,
            "payment_method": "ach",
            "amount_cents": 1000,
            "expected_fee_version": assessed["version"],
        },
    )
    assert paid.status_code == 201
    assert (await api_client.delete(f"/api/v1/filings/{fid}/documents/{doc.id}")).status_code == 204
    replacement = await api_client.post(
        f"/api/v1/filings/{fid}/documents",
        headers={"Idempotency-Key": str(uuid4())},
        data={
            "title": "Corrected complaint",
            "document_type_code": "COMPLAINT",
        },
        files={"file": ("corrected.pdf", decision_pdf(), "application/pdf")},
    )
    assert replacement.status_code == 200, replacement.text
    current = (await api_client.get(f"/api/v1/filings/{fid}/fees")).json()
    assert current["assessment_stale"] and current["total_cents"] is None
    assert current["paid_cents"] == 1000 and not current["obligation_met"]
    assert (await api_client.post(
        f"/api/v1/filings/{fid}/submit",
        json=await submission_review(api_client, fid),
    )).status_code == 402
    assert (
        await api_client.get(f"/api/v1/documents/{doc.id}/download")
    ).content == b"Synthetic Complaint"
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    higher = await api_client.post(
        f"/api/v1/clerk/filings/{fid}/fees", json=assessment(current["version"], 1500)
    )
    assert higher.status_code == 201, higher.text
    fees = higher.json()
    assert fees["balance_due_cents"] == 500 and fees["paid_cents"] == 1000
    api_client.headers["X-Demo-User-Id"] = str(filer)
    supplemental = await api_client.post(
        "/api/v1/payments/process",
        json={
            "envelope_id": fid,
            "payment_method": "credit_card",
            "amount_cents": 500,
            "expected_fee_version": fees["version"],
        },
    )
    assert supplemental.status_code == 201, supplemental.text
    second_payment = await db_session.get(Payment, supplemental.json()["id"])
    assert second_payment.fee_basis["previous_paid_cents"] == 1000
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    lower = await api_client.post(
        f"/api/v1/clerk/filings/{fid}/fees", json=assessment(fees["version"], 1200)
    )
    assert lower.status_code == 201, lower.text
    assert lower.json()["overpaid_cents"] == 300 and lower.json()["balance_due_cents"] == 0
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(Payment)
            .where(
                Payment.status == PaymentStatus.REFUNDED,
            )
        )
        == 0
    )
    await db_session.refresh(first)  # Compare the stored row, not the cached object.
    assert first.details == first_details
    api_client.headers["X-Demo-User-Id"] = str(filer)
    assert (await api_client.post(
        f"/api/v1/filings/{fid}/submit",
        json=await submission_review(api_client, fid),
    )).status_code == 200
    receipt = (await api_client.get(f"/api/v1/filings/{fid}/history")).json()["transactions"][0]
    assert [payment["amount_cents"] for payment in receipt["details"]["payments"]] == [1000, 500]
    assert receipt["details"]["fee_assessment"]["overpaid_cents"] == 300


async def test_balance_ignores_invalid_credits_and_demo_funds_in_production(
    db_session,
    api_client,
    fee_filing,
    monkeypatch,
):
    fid, filer, clerk, other, _ = fee_filing
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    assert (
        await api_client.post(f"/api/v1/clerk/filings/{fid}/fees", json=assessment(0, 1000))
    ).status_code == 201
    filing = await filing_service.get_filing(db_session, fid)
    for amount, status, payer, envelope, simulated in [
        (300, PaymentStatus.COMPLETED, filer, fid, True),
        (200, PaymentStatus.COMPLETED, filer, fid, False),
        (1000, PaymentStatus.FAILED, filer, fid, False),
        (1000, PaymentStatus.PENDING, filer, fid, False),
        (1000, PaymentStatus.REFUNDED, filer, fid, False),
        (1000, PaymentStatus.WAIVED, filer, fid, False),
        (1000, PaymentStatus.COMPLETED, other, fid, False),
        (-1000, PaymentStatus.COMPLETED, filer, fid, False),
        (1000, PaymentStatus.COMPLETED, filer, None, False),
    ]:
        payment = Payment(
            amount_cents=amount,
            status=status,
            payer_id=payer,
            envelope_id=envelope,
            is_simulated=simulated,
        )
        db_session.add(payment)
    await db_session.flush()
    filing.payment_id = payment.id  # The legacy pointer is not proof of a paid balance.
    await db_session.flush()
    demo = await fee_state(db_session, filing, filer)
    assert demo.paid_cents == 500 and demo.balance_due_cents == 500 and not demo.obligation_met
    monkeypatch.setattr(settings, "allow_demo_mode", False)
    production = await fee_state(db_session, filing, filer)
    assert production.paid_cents == 200 and production.balance_due_cents == 800
    assert not production.obligation_met and not production.payments_simulated
    app.dependency_overrides[get_current_user_id] = lambda: filer
    try:
        unavailable = await api_client.post(
            "/api/v1/payments/process",
            json={
                "envelope_id": fid,
                "payment_method": "credit_card",
                "amount_cents": 800,
                "expected_fee_version": production.version,
            },
        )
        assert unavailable.status_code == 503, unavailable.text
        assert await db_session.scalar(select(func.count()).select_from(Payment)) == 9
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)
    # A later signed waiver decision controls the balance, not an old manual assessment.
    filing.fee_version += 1
    filing.fee_waiver_requested = True
    filing.fee_waiver_granted = True
    waived = await fee_state(db_session, filing, filer)
    assert waived.obligation_met and waived.source == "waiver"
    assert waived.assessment_id is None and not waived.assessment_stale
    filing.fee_waiver_granted = False
    filing.fee_waiver_amount_due_cents = 750
    denied = await fee_state(db_session, filing, filer)
    assert denied.balance_due_cents == 550 and denied.can_pay
    assert denied.assessment_id is None and not denied.assessment_stale


async def test_unassessed_fees_do_not_infer_a_motion_or_trust_seeded_zero_in_production(
    db_session,
    fee_filing,
    monkeypatch,
):
    fid, filer, _, _, _ = fee_filing
    filing = await filing_service.get_filing(db_session, fid)
    filing.filing_type = "subsequent"
    unknown = await fee_state(db_session, filing, filer)
    assert unknown.total_cents is None and not unknown.obligation_met
    case_type = await db_session.get(CaseType, filing.case_type_id)
    case_type.filing_fee_cents = 0
    filing.filing_type = "initial"
    monkeypatch.setattr(settings, "allow_demo_mode", False)
    unknown = await fee_state(db_session, filing, filer)
    assert unknown.total_cents is None and not unknown.obligation_met
    filing.filing_type = "service_only"
    service = await fee_state(db_session, filing, filer)
    assert service.total_cents == 0 and service.obligation_met and not service.can_request_review


async def test_court_authority_waiver_and_payload_guards(db_session, api_client, fee_filing):
    fid, filer, clerk, other, _ = fee_filing
    filing = await filing_service.get_filing(db_session, fid)
    for actor in (filer, other):
        api_client.headers["X-Demo-User-Id"] = str(actor)
        assert (
            await api_client.post(f"/api/v1/clerk/filings/{fid}/fees", json=assessment(0, 0))
        ).status_code == 403
    outsider = await db_session.get(User, other)
    outsider.user_type = UserType.ADMIN
    await db_session.flush()
    assert (
        await api_client.post(f"/api/v1/clerk/filings/{fid}/fees", json=assessment(0, 0))
    ).status_code == 403
    api_client.headers["X-Demo-User-Id"] = str(clerk)
    for invalid in (
        {"reviewed": False},
        {"items": []},
        {"authority_reference": " "},
        {"items": [{"fee_type": "fee", "description": "charge", "amount_cents": -1}]},
    ):
        assert (
            await api_client.post(
                f"/api/v1/clerk/filings/{fid}/fees",
                json={
                    **assessment(0, 0),
                    **invalid,
                },
            )
        ).status_code == 422
    filing.filer_id = clerk
    await db_session.flush()
    assert (
        await api_client.post(f"/api/v1/clerk/filings/{fid}/fees", json=assessment(0, 0))
    ).status_code == 403
    filing.filer_id = filer
    filing.fee_waiver_requested = True
    await db_session.flush()
    assert (
        await api_client.post(f"/api/v1/clerk/filings/{fid}/fees", json=assessment(0, 0))
    ).status_code == 409
    filing.fee_waiver_granted = False
    filing.fee_waiver_amount_due_cents = 750
    await db_session.flush()
    assert (
        await api_client.post(f"/api/v1/clerk/filings/{fid}/fees", json=assessment(0, 0))
    ).status_code == 409
    api_client.headers["X-Demo-User-Id"] = str(filer)
    assert (
        await api_client.post(
            "/api/v1/payments/process",
            json={
                "envelope_id": fid,
                "payment_method": "waiver",
                "amount_cents": 750,
                "expected_fee_version": 0,
            },
        )
    ).status_code == 422
    assert await db_session.scalar(select(func.count()).select_from(FilingTransaction)) == 0


@pytest.mark.parametrize("operation", ["request", "assess"])
@pytest.mark.parametrize("failure", ["storage", "audit"])
async def test_failed_review_does_not_retain_a_partial_assessment(
    db_session,
    api_client,
    fee_filing,
    monkeypatch,
    operation,
    failure,
):
    fid, filer, clerk, _, doc = fee_filing
    doc_id = doc.id
    if failure == "storage":
        document_service.upload_document(b"Changed bytes", doc.file_key, "text/plain")
    else:

        async def fail_audit(*args, **kwargs):
            raise RuntimeError("Audit storage unavailable")

        monkeypatch.setattr(audit_service, "log_action", fail_audit)
    api_client.headers["X-Demo-User-Id"] = str(filer if operation == "request" else clerk)
    url = (
        f"/api/v1/filings/{fid}/fee-review"
        if operation == "request"
        else f"/api/v1/clerk/filings/{fid}/fees"
    )
    body = (
        {"expected_version": 0, "reason": "Review exemption"}
        if operation == "request"
        else assessment(0, 750)
    )
    if failure == "storage":
        response = await api_client.post(url, json=body)
        assert response.status_code == 409 and "fingerprint" in response.text
    else:
        with pytest.raises(RuntimeError, match="Audit storage unavailable"):
            await api_client.post(url, json=body)
    filing = await filing_service.get_filing(db_session, fid, for_update=True)
    assert filing.fee_version == 0 and filing.fee_assessment_id is None
    assert filing.fee_review_requested_at is None and filing.submitted_at is None
    assert next(item for item in filing.documents if item.id == doc_id).retained_at is None
    assert await db_session.scalar(select(func.count()).select_from(FilingTransaction)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Notification)) == 0
