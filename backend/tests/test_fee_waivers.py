"""Exercise independent, nonpublic waiver decisions and the filer's payment path."""

import io
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from pypdf import PdfWriter
from sqlalchemy import func, select

from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.notification import Notification
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import document_service, filing_service
from app.services.fee_assessment_service import fee_state


def decision_pdf():
    out = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(out)
    return out.getvalue()


@pytest_asyncio.fixture
async def waiver_case(db_session, api_client, tmp_path, monkeypatch, stored_document):
    monkeypatch.setattr(document_service, "_local_storage_path", lambda: tmp_path)
    court = Court(name="Waiver Court", county="Wayne", court_type=CourtType.CIRCUIT)
    other_court = Court(name="Other Court", county="Kent", court_type=CourtType.CIRCUIT)
    users = [
        User(
            email=f"waiver-{i}@test.com",
            first_name=kind.value,
            last_name="Reviewer",
            user_type=kind,
        )
        for i, kind in enumerate(
            [
                UserType.ATTORNEY,
                UserType.CLERK,
                UserType.JUDGE,
                UserType.JUDGE,
                UserType.ADMIN,
            ]
        )
    ]
    db_session.add_all([court, other_court, *users])
    await db_session.flush()
    case_type = CaseType(
        court_id=court.id,
        code="CIV",
        name="Civil",
        category=CaseCategory.CIVIL,
        filing_fee_cents=18000,
    )
    db_session.add(case_type)
    for user, cid, role in [
        (users[1], court.id, CourtRole.CLERK),
        (users[2], court.id, CourtRole.JUDGE),
        (users[3], other_court.id, CourtRole.JUDGE),
        (users[4], court.id, CourtRole.ADMIN),
    ]:
        db_session.add(UserCourtRole(user_id=user.id, court_id=cid, role=role))
    await db_session.flush()
    filing = FilingEnvelope(
        court_id=court.id,
        case_type_id=case_type.id,
        filer_id=users[0].id,
        filing_type="initial",
        case_title="Private request",
        fee_waiver_requested=True,
        fee_waiver_reason="legacy private text",
    )
    db_session.add(filing)
    await db_session.flush()
    db_session.add(stored_document(filing.id))
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(users[0].id)
    return filing, users, case_type


async def submit_application(api_client, filing):
    uploaded = await api_client.post(
        f"/api/v1/filings/{filing.id}/documents",
        data={
            "document_type_code": "FEE_WAIVER",
            "title": "MC 20 private application",
        },
        files={"file": ("mc20.pdf", decision_pdf(), "application/pdf")},
    )
    assert uploaded.status_code == 200, uploaded.text
    submitted = await api_client.post(f"/api/v1/filings/{filing.id}/submit")
    assert submitted.status_code == 200, submitted.text


async def test_application_required_and_clerk_referral_has_no_filing_decision(
    waiver_case,
    api_client,
    db_session,
):
    filing, users, _ = waiver_case
    missing = await api_client.post(f"/api/v1/filings/{filing.id}/submit")
    assert missing.status_code == 400 and "MC 20" in missing.text
    await submit_application(api_client, filing)
    endpoint = f"/api/v1/clerk/filings/{filing.id}/fee-waiver"
    for user in [users[0], users[3], users[4]]:
        api_client.headers["X-Demo-User-Id"] = str(user.id)
        denied = await api_client.post(endpoint, data={"action": "refer"})
        assert denied.status_code == 403
    api_client.headers["X-Demo-User-Id"] = str(users[1].id)
    no_judicial_authority = await api_client.post(endpoint, data={"action": "deny_judicial"})
    assert no_judicial_authority.status_code == 403
    result = await api_client.post(endpoint, data={"action": "refer"})
    assert result.status_code == 200
    assert result.json()["status"] == "submitted"
    assert result.json()["fee_waiver_granted"] is None
    assert (await api_client.post(endpoint, data={"action": "refer"})).status_code == 403
    history = (await api_client.get(f"/api/v1/filings/{filing.id}/history")).json()
    assert history["fee_waiver"]["allowed_actions"] == []
    assert history["transactions"][0]["event_type"] == "waiver_referred"
    api_client.headers["X-Demo-User-Id"] = str(users[2].id)
    history = (await api_client.get(f"/api/v1/filings/{filing.id}/history")).json()
    assert set(history["fee_waiver"]["allowed_actions"]) == {"grant_judicial", "deny_judicial"}
    await filing_service.review_filing(
        db_session, filing.id, users[1].id, "accept", expected_submission_count=1
    )
    queue = await api_client.get(
        "/api/v1/clerk/queue",
        params={
            "court_id": filing.court_id,
            "fee_waivers": True,
        },
    )
    assert queue.json()["total"] == 1  # An accepted filing can still await a waiver decision.
    assert queue.json()["filings"][0]["fee_waiver_granted"] is None


@pytest.mark.parametrize(
    "action,actor_index",
    [
        ("grant_public_assistance", 1),
        ("grant_legal_services", 1),
        ("grant_judicial", 2),
    ],
)
async def test_signed_grants_are_private_retained_and_independent(
    waiver_case,
    api_client,
    db_session,
    action,
    actor_index,
):
    filing, users, _ = waiver_case
    await submit_application(api_client, filing)
    api_client.headers["X-Demo-User-Id"] = str(users[actor_index].id)
    endpoint = f"/api/v1/clerk/filings/{filing.id}/fee-waiver"
    assert (await api_client.post(endpoint, data={"action": action})).status_code == 400
    assert (
        await api_client.post(
            endpoint,
            data={"action": action},
            files={
                "file": ("fake.pdf", b"plain text", "application/pdf"),
            },
        )
    ).status_code in (415, 422)
    result = await api_client.post(
        endpoint,
        data={"action": action},
        files={
            "file": ("signed.pdf", decision_pdf(), "application/pdf"),
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["fee_waiver_granted"] is True
    assert result.json()["status"] == "submitted"
    assert result.json()["fee_waiver_decided_at"] is not None
    assert not any(
        d["document_type_code"] == "FEE_WAIVER_ORDER" for d in result.json()["documents"]
    )
    assert (await api_client.post(endpoint, data={"action": action})).status_code == 409
    order = await db_session.scalar(
        select(FilingDocument).where(
            FilingDocument.document_type_code == "FEE_WAIVER_ORDER",
        )
    )
    assert order.is_confidential and order.retained_at is not None
    history = (await api_client.get(f"/api/v1/filings/{filing.id}/history")).json()
    assert history["transactions"][0]["details"]["documents"][0]["id"] == order.id
    api_client.headers["X-Demo-User-Id"] = str(users[0].id)
    download = await api_client.get(f"/api/v1/documents/{order.id}/download")
    assert download.status_code == 200 and download.content == decision_pdf()
    await filing_service.review_filing(
        db_session, filing.id, users[1].id, "return", "Correct title", expected_submission_count=1
    )
    cannot_remove = await api_client.delete(f"/api/v1/filings/{filing.id}/documents/{order.id}")
    assert cannot_remove.status_code == 404
    assert (
        await api_client.post(
            "/api/v1/payments/process",
            json={
                "envelope_id": filing.id,
                "payment_method": "credit_card",
                "amount_cents": 18000,
                "expected_fee_version": filing.fee_version,
            },
        )
    ).status_code == 409
    api_client.headers["X-Demo-User-Id"] = str(users[3].id)
    assert (await api_client.get(f"/api/v1/documents/{order.id}/download")).status_code == 403
    assert (await api_client.get(f"/api/v1/filings/{filing.id}/history")).status_code == 403


async def test_denial_can_be_paid_without_resubmission_or_fee_recalculation(
    waiver_case,
    api_client,
    db_session,
):
    filing, users, case_type = waiver_case
    await submit_application(api_client, filing)
    received_at = filing.submitted_at
    api_client.headers["X-Demo-User-Id"] = str(users[2].id)
    endpoint = f"/api/v1/clerk/filings/{filing.id}/fee-waiver"
    body = {"action": "deny_judicial", "reason": " ", "amount_due_cents": "750"}
    assert (await api_client.post(endpoint, data=body)).status_code == 400
    body["reason"] = "Reason in the private order"
    denied = await api_client.post(
        endpoint,
        data=body,
        files={
            "file": ("denial.pdf", decision_pdf(), "application/pdf"),
        },
    )
    assert denied.status_code == 200, denied.text
    assert not (await fee_state(db_session, filing)).obligation_met
    case_type.filing_fee_cents = 0
    await db_session.flush()
    assert not (await fee_state(db_session, filing)).obligation_met
    await filing_service.review_filing(
        db_session, filing.id, users[1].id, "return", "Correct title", expected_submission_count=1
    )
    api_client.headers["X-Demo-User-Id"] = str(users[0].id)
    assert (
        await api_client.patch(
            f"/api/v1/filings/{filing.id}",
            json={
                "fee_waiver_requested": False,
            },
        )
    ).status_code == 409
    assert (await api_client.post(f"/api/v1/filings/{filing.id}/submit")).status_code == 402
    # Acceptance does not override denial; payment can be received afterward, too.
    filing.status = FilingStatus.SUBMITTED
    await db_session.flush()
    await filing_service.review_filing(
        db_session, filing.id, users[1].id, "accept", expected_submission_count=1
    )
    assert filing.fee_waiver_granted is False
    case_type.filing_fee_cents = 99000
    await db_session.flush()
    payment = {"envelope_id": filing.id, "payment_method": "credit_card", "amount_cents": 750,
               "expected_fee_version": filing.fee_version}
    assert (
        await api_client.post(
            "/api/v1/payments/process",
            json={
                **payment,
                "amount_cents": 99000,
            },
        )
    ).status_code == 400
    paid = await api_client.post("/api/v1/payments/process", json=payment)
    assert paid.status_code == 201, paid.text
    assert (await api_client.post("/api/v1/payments/process", json=payment)).status_code == 409
    assert filing.status == FilingStatus.ACCEPTED
    assert filing.submitted_at == received_at and filing.submission_count == 1
    history = (await api_client.get(f"/api/v1/filings/{filing.id}/history")).json()
    assert history["fee_waiver"]["can_pay"] is False
    assert history["transactions"][0]["event_type"] == "payment_recorded"
    assert history["transactions"][0]["details"]["payment"]["amount_cents"] == 750
    notices = list(await db_session.scalars(select(Notification.body)))
    assert not any("Reason in the private order" in notice for notice in notices)
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(FilingTransaction)
            .where(
                FilingTransaction.event_type == "waiver_denied",
            )
        )
        == 1
    )


async def test_judge_cannot_decide_own_application(waiver_case, api_client, db_session):
    filing, users, _ = waiver_case
    filing.filer_id = users[2].id
    filing.submitted_at = datetime.now(UTC)
    filing.status = FilingStatus.SUBMITTED
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(users[2].id)
    response = await api_client.post(
        f"/api/v1/clerk/filings/{filing.id}/fee-waiver", data={"action": "grant_judicial"}
    )
    assert response.status_code == 403


async def test_failed_decision_does_not_keep_an_order_or_change_waiver(
    waiver_case, api_client, db_session, monkeypatch, tmp_path,
):
    from app.api import fee_waivers

    filing, users, _ = waiver_case
    await submit_application(api_client, filing)
    fid = filing.id
    api_client.headers["X-Demo-User-Id"] = str(users[1].id)
    before = {p for p in tmp_path.rglob("*") if p.is_file()}

    async def unavailable(*args, **kwargs):
        raise RuntimeError("Audit store unavailable")

    monkeypatch.setattr(fee_waivers.audit_service, "log_action", unavailable)
    with pytest.raises(RuntimeError, match="Audit store unavailable"):
        # Match the request transaction rollback supplied by get_db in production.
        async with db_session.begin_nested():
            await api_client.post(f"/api/v1/clerk/filings/{fid}/fee-waiver", data={
                "action": "grant_public_assistance",
            }, files={"file": ("signed.pdf", decision_pdf(), "application/pdf")})
    assert {p for p in tmp_path.rglob("*") if p.is_file()} == before
    unchanged = await filing_service.get_filing(db_session, fid)
    assert unchanged.fee_waiver_granted is None
    assert unchanged.fee_waiver_decided_at is None
    assert await db_session.scalar(select(func.count()).select_from(FilingTransaction)) == 1
    assert await db_session.scalar(select(func.count()).select_from(Notification)) == 1
