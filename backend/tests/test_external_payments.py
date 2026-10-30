"""External receipt credits preserve balances, source evidence and court boundaries."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import Depends
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.api.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.main import app
from app.models.filing import FilingEnvelope
from app.models.filing_transaction import FilingTransaction
from app.models.payment import Payment
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import audit_service
from tests.filing_requests import submission_review
from tests.test_fee_assessments import assessment
from tests.test_fee_assessments import fee_filing as fee_filing


def external_receipt(fee_version=1, payment_version=0, amount=1000, reference="SYN-RECEIPT-1"):
    return {
        "expected_fee_version": fee_version,
        "expected_payment_version": payment_version,
        "amount_cents": amount,
        "receipt_system": "Synthetic court cashier",
        "receipt_reference": reference,
        "received_at": "2026-01-01T12:00:00-05:00",
        "reason": "Verified the external receipt and allocation to this filing",
        "verified": True,
    }


@pytest_asyncio.fixture
async def external_filing(fee_filing, db_session, api_client, monkeypatch):
    fid, filer, clerk, other, doc = fee_filing
    filing = await db_session.get(FilingEnvelope, fid)
    db_session.add(UserCourtRole(user_id=clerk, court_id=filing.court_id, role=CourtRole.ADMIN))
    await db_session.flush()
    actor = {"id": clerk}

    async def actor_account(db=Depends(get_db, scope="function")):
        return await db.get(User, actor["id"])

    monkeypatch.setitem(app.dependency_overrides, get_current_user, actor_account)
    monkeypatch.setattr(settings, "external_payments_enabled", True)
    monkeypatch.setattr(settings, "allow_demo_mode", False)
    response = await api_client.post(f"/api/v1/clerk/filings/{fid}/fees", json=assessment(0, 1000))
    assert response.status_code == 201, response.text
    return fid, filer, clerk, other, actor


async def test_partial_credits_replay_submission_and_reversal_retain_the_original_receipt(
    external_filing,
    db_session,
    api_client,
):
    fid, filer, clerk, _, actor = external_filing
    base = f"/api/v1/filings/{fid}"
    actor["id"] = filer
    old_review = await submission_review(api_client, fid)
    actor["id"] = clerk
    key = {"Idempotency-Key": str(uuid4())}
    request = external_receipt(amount=600)
    first = await api_client.post(f"{base}/external-payments", json=request, headers=key)
    assert first.status_code == 201, first.text
    payment = first.json()
    assert not payment["is_simulated"]
    assert payment["external_receipt"]["received_at"] == "2026-01-01T17:00:00+00:00"
    replay = await api_client.post(f"{base}/external-payments", json=request, headers=key)
    assert replay.status_code == 200 and replay.json() == payment
    assert (
        await api_client.post(
            f"{base}/external-payments", json={**request, "amount_cents": 500}, headers=key
        )
    ).status_code == 409
    fees = (await api_client.get(f"{base}/fees")).json()
    assert (fees["paid_cents"], fees["balance_due_cents"], fees["payment_version"]) == (600, 400, 1)
    assert not fees["assessment_stale"] and fees["version"] == 1
    second = await api_client.post(
        f"{base}/external-payments",
        json=external_receipt(payment_version=1, amount=400, reference="SYN-RECEIPT-2"),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert second.status_code == 201, second.text
    actor["id"] = filer
    assert (await api_client.post(f"{base}/submit", json=old_review)).status_code == 409
    submitted = await api_client.post(
        f"{base}/submit", json=await submission_review(api_client, fid)
    )
    assert submitted.status_code == 200, submitted.text
    receipt = await db_session.scalar(
        select(FilingTransaction).where(
            FilingTransaction.filing_id == fid, FilingTransaction.event_type == "submitted"
        )
    )
    original = deepcopy(receipt.details)
    assert original["fee_assessment"]["paid_cents"] == 1000
    assert original["payments"][0]["external_receipt"]["reference"] == "SYN-RECEIPT-1"
    actor["id"] = clerk
    reversal = {
        "expected_payment_version": 2,
        "reason": "External receipt was allocated to the wrong filing",
        "reviewed": True,
    }
    reverse_url = f"{base}/external-payments/{payment['id']}/reverse"
    reversed_credit = await api_client.post(reverse_url, json=reversal)
    assert reversed_credit.status_code == 200, reversed_credit.text
    assert reversed_credit.json()["status"] == "reversed"
    assert (await api_client.post(reverse_url, json=reversal)).status_code == 200
    replay = await api_client.post(f"{base}/external-payments", json=request, headers=key)
    assert replay.status_code == 200 and replay.json()["status"] == "reversed"
    fees = (await api_client.get(f"{base}/fees")).json()
    assert (fees["paid_cents"], fees["balance_due_cents"], fees["payment_version"]) == (400, 600, 3)
    assert not fees["assessment_stale"]
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 2
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(FilingTransaction)
            .where(FilingTransaction.event_type == "fee_payment_reversed")
        )
        == 1
    )
    await db_session.refresh(receipt)
    assert receipt.details == original
    records = (await api_client.get(f"{base}/payments")).json()
    assert records["payment_version"] == 3
    assert records["total"] == 2 and records["payments"][1]["status"] == "reversed"


async def test_credit_and_reversal_invalidate_review_without_changing_the_fee_assessment(
    external_filing,
    api_client,
):
    fid, _, _, _, _ = external_filing
    base = f"/api/v1/filings/{fid}"
    request = external_receipt()
    first = await api_client.post(
        f"{base}/external-payments", json=request, headers={"Idempotency-Key": str(uuid4())}
    )
    review = await submission_review(api_client, fid)
    reversed_credit = await api_client.post(
        f"{base}/external-payments/{first.json()['id']}/reverse",
        json={"expected_payment_version": 0, "reason": "Wrong allocation", "reviewed": True},
    )
    assert reversed_credit.status_code == 409
    assert (
        await api_client.post(
            f"{base}/external-payments/{first.json()['id']}/reverse",
            json={"expected_payment_version": 1, "reason": "Wrong allocation", "reviewed": True},
        )
    ).status_code == 200
    assert await submission_review(api_client, fid) != review
    fees = (await api_client.get(f"{base}/fees")).json()
    assert (
        fees["balance_due_cents"] == 1000 and fees["version"] == 1 and not fees["assessment_stale"]
    )


@pytest.mark.parametrize("identity", ["filer", "unassigned_admin", "clerk"])
async def test_only_a_separate_assigned_court_administrator_can_credit(
    external_filing,
    db_session,
    api_client,
    identity,
):
    fid, filer, clerk, other, actor = external_filing
    if identity == "unassigned_admin":
        (await db_session.get(User, other)).user_type = UserType.ADMIN
        actor["id"] = other
    elif identity == "clerk":
        await db_session.execute(
            text("DELETE FROM user_court_roles WHERE user_id=:id AND role='ADMIN'"), {"id": clerk}
        )
    else:
        filing = await db_session.get(FilingEnvelope, fid)
        db_session.add(UserCourtRole(user_id=filer, court_id=filing.court_id, role=CourtRole.ADMIN))
        actor["id"] = filer
    response = await api_client.post(
        f"/api/v1/filings/{fid}/external-payments",
        json=external_receipt(),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 403
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 0
    if identity == "unassigned_admin":
        assert (await api_client.get(f"/api/v1/filings/{fid}/payments")).status_code == 403


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"expected_fee_version": 0}, 409),
        ({"expected_payment_version": 1}, 409),
        ({"amount_cents": 1001}, 409),
        ({"receipt_reference": " "}, 422),
        ({"verified": False}, 422),
        ({"received_at": "2026-01-01T12:00:00"}, 422),
    ],
)
async def test_invalid_or_stale_external_credit_cannot_change_the_balance(
    external_filing,
    db_session,
    api_client,
    change,
    expected,
):
    fid = external_filing[0]
    response = await api_client.post(
        f"/api/v1/filings/{fid}/external-payments",
        json={**external_receipt(), **change},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == expected, response.text
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 0


async def test_disabled_recording_future_receipts_and_missing_retry_keys_are_rejected(
    external_filing,
    api_client,
    monkeypatch,
):
    url = f"/api/v1/filings/{external_filing[0]}/external-payments"
    assert (await api_client.post(url, json=external_receipt())).status_code == 422
    request = {
        **external_receipt(),
        "received_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    }
    assert (
        await api_client.post(url, json=request, headers={"Idempotency-Key": str(uuid4())})
    ).status_code == 422
    monkeypatch.setattr(settings, "external_payments_enabled", False)
    assert (
        await api_client.post(
            url, json=external_receipt(), headers={"Idempotency-Key": str(uuid4())}
        )
    ).status_code == 503


async def test_audit_failure_rolls_back_credit_balance_and_notice(
    external_filing, db_session, api_client, monkeypatch
):
    fid = external_filing[0]

    async def unavailable(*args, **kwargs):
        raise RuntimeError("Audit storage unavailable")

    monkeypatch.setattr(audit_service, "log_action", unavailable)
    with pytest.raises(RuntimeError, match="Audit storage unavailable"):
        await api_client.post(
            f"/api/v1/filings/{fid}/external-payments",
            json=external_receipt(),
            headers={"Idempotency-Key": str(uuid4())},
        )
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 0
    assert (await db_session.get(FilingEnvelope, fid)).payment_version == 0
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(FilingTransaction)
            .where(FilingTransaction.event_type == "fee_payment_recorded")
        )
        == 0
    )


@pytest.mark.parametrize("mutation", ["UPDATE payments SET amount_cents=1", "DELETE FROM payments"])
async def test_external_receipt_evidence_cannot_be_edited_or_deleted(
    external_filing,
    db_session,
    api_client,
    mutation,
):
    response = await api_client.post(
        f"/api/v1/filings/{external_filing[0]}/external-payments",
        json=external_receipt(),
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    with pytest.raises(IntegrityError, match="External payment evidence is retained"):
        async with db_session.begin_nested():
            await db_session.execute(text(mutation))
