"""Use the same fee total for quotes, payment, and submission."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.court import CaseCategory, CaseType, Court, CourtType, FeeSchedule
from app.models.filing import FilingEnvelope
from app.models.payment import Payment
from app.models.user import User, UserType


@pytest.mark.parametrize("additional_cents", [0, 750])
async def test_zero_base_fee_submission_uses_full_quote(
    db_session, api_client, additional_cents, stored_document,
):
    court = Court(name="Fee Court", county="Wayne", court_type=CourtType.CIRCUIT)
    filer = User(email="fees@test.com", first_name="Fee", last_name="Filer",
                 user_type=UserType.ATTORNEY)
    db_session.add_all([court, filer])
    await db_session.flush()
    case_type = CaseType(court_id=court.id, code="FREE", name="Free base",
                         category=CaseCategory.CIVIL, filing_fee_cents=0)
    db_session.add(case_type)
    db_session.add(FeeSchedule(court_id=court.id, fee_type="additional",
                               amount_cents=additional_cents, effective_date=date(2026, 1, 1)))
    await db_session.flush()
    other_type = CaseType(court_id=court.id, code="OTHER", name="Other",
                          category=CaseCategory.CIVIL)
    db_session.add(other_type)
    await db_session.flush()
    db_session.add(FeeSchedule(
        court_id=court.id, case_type_id=other_type.id, fee_type="other case fee",
        amount_cents=10000, effective_date=date(2026, 1, 1),
    ))
    db_session.add(FeeSchedule(
        court_id=court.id, fee_type="future fee", amount_cents=20000,
        effective_date=datetime.now(UTC) + timedelta(days=1),
    ))
    filing = FilingEnvelope(court_id=court.id, case_type_id=case_type.id,
                            filer_id=filer.id, case_title="Free v Fee", filing_type="initial")
    db_session.add(filing)
    await db_session.flush()
    db_session.add(stored_document(filing.id))
    await db_session.flush()
    api_client.headers["X-Demo-User-Id"] = str(filer.id)
    quote = await api_client.post("/api/v1/payments/calculate", json={
        "court_id": court.id, "case_type_id": case_type.id,
    })
    assert quote.status_code == 200
    assert quote.json()["total_cents"] == additional_cents
    submitted = await api_client.post(f"/api/v1/filings/{filing.id}/submit")
    if additional_cents:
        assert submitted.status_code == 402
        payment = {"envelope_id": filing.id, "payment_method": "credit_card",
                   "amount_cents": additional_cents}
        wrong_amount = await api_client.post("/api/v1/payments/process", json={
            **payment, "amount_cents": additional_cents - 1,
        })
        assert wrong_amount.status_code == 400
        paid = await api_client.post("/api/v1/payments/process", json=payment)
        assert paid.status_code == 201
        duplicate = await api_client.post("/api/v1/payments/process", json=payment)
        assert duplicate.status_code == 409
        submitted = await api_client.post(f"/api/v1/filings/{filing.id}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    payment_count = await db_session.scalar(select(func.count()).select_from(Payment))
    assert payment_count == bool(additional_cents)
    late_payment = await api_client.post("/api/v1/payments/process", json={
        "envelope_id": filing.id, "payment_method": "credit_card", "amount_cents": 1,
    })
    assert late_payment.status_code == 409

    # Service-only quotes remain free even when this court has additional fees.
    service_quote = await api_client.post("/api/v1/payments/calculate", json={
        "court_id": court.id, "case_type_id": case_type.id, "filing_type": "service_only",
    })
    assert service_quote.json()["total_cents"] == 0
    assert service_quote.json()["additional_fees"] == []
    mismatch = await api_client.post("/api/v1/payments/calculate", json={
        "court_id": court.id + 1, "case_type_id": case_type.id,
    })
    assert mismatch.status_code == 400
