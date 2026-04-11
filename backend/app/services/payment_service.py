from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.court import CaseType, FeeSchedule
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.schemas.payment import PaymentCalculateResponse


async def calculate_fees(
    db: AsyncSession,
    court_id: int,
    case_type_id: int,
    document_count: int = 1,
) -> PaymentCalculateResponse:
    # Get base filing fee from case type
    result = await db.execute(
        select(CaseType).where(CaseType.id == case_type_id)
    )
    case_type = result.scalar_one_or_none()
    base_fee = case_type.filing_fee_cents if case_type else 0

    # Get additional fees from fee schedule
    fee_result = await db.execute(
        select(FeeSchedule).where(
            FeeSchedule.court_id == court_id,
            FeeSchedule.is_active == True,  # noqa: E712
        )
    )
    additional_fees = []
    extra_total = 0
    for fee in fee_result.scalars().all():
        additional_fees.append({
            "fee_type": fee.fee_type,
            "amount_cents": fee.amount_cents,
            "description": fee.description or fee.fee_type,
        })
        extra_total += fee.amount_cents

    total = base_fee + extra_total

    return PaymentCalculateResponse(
        filing_fee_cents=base_fee,
        additional_fees=additional_fees,
        total_cents=total,
        fee_description=f"Filing fee for {case_type.name}" if case_type else "Filing fee",
        is_simulated=settings.payments_are_simulated,
        simulation_notice=(
            "Fees are calculated from court schedules. "
            "No payment processor is connected; amounts are not charged."
            if settings.payments_are_simulated
            else ""
        ),
    )


async def process_payment(
    db: AsyncSession,
    amount_cents: int,
    payment_method: PaymentMethod,
    payer_id: int,
    description: str | None = None,
) -> Payment:
    # Court compliance: PSP integration must replace this; keep audit text explicit.
    desc = description or ""
    if settings.payments_are_simulated:
        desc = f"[SIMULATED — no funds moved] {desc}".strip()

    payment = Payment(
        amount_cents=amount_cents,
        status=PaymentStatus.COMPLETED,  # Replace when wiring a real PSP + webhooks
        payment_method=payment_method,
        payer_id=payer_id,
        description=desc,
        transaction_ref=(
            f"MUEFS-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
            f"-{payer_id}"
        ),
        processed_at=datetime.now(UTC),
    )
    db.add(payment)
    await db.flush()
    return payment
