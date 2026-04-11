"""Tests for payment-related functionality."""

import pytest

from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.payment import PaymentMethod, PaymentStatus
from app.services import payment_service


@pytest.mark.asyncio
async def test_calculate_fees(db_session):
    court = Court(name="Test Court", county="Test", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()

    case_type = CaseType(
        court_id=court.id,
        code="CIV",
        name="Civil - General",
        category=CaseCategory.CIVIL,
        filing_fee_cents=17500,
    )
    db_session.add(case_type)
    await db_session.flush()

    result = await payment_service.calculate_fees(db_session, court.id, case_type.id)
    assert result.filing_fee_cents == 17500
    assert result.total_cents >= 17500
    assert result.is_simulated is True
    notice = result.simulation_notice.lower()
    assert "simulation" in notice or "processor" in notice


@pytest.mark.asyncio
async def test_process_payment(db_session):
    payment = await payment_service.process_payment(
        db_session,
        amount_cents=17500,
        payment_method=PaymentMethod.CREDIT_CARD,
        payer_id=1,
        description="Test filing fee",
    )

    assert payment.id is not None
    assert payment.amount_cents == 17500
    assert payment.status == PaymentStatus.COMPLETED
    assert payment.transaction_ref is not None
    assert payment.processed_at is not None
    assert "[SIMULATED" in (payment.description or "")
