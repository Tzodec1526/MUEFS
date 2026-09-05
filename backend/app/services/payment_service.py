from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.court import CaseCategory, CaseType, Court, CourtType, FeeSchedule
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.schemas.payment import FeeItem, PaymentCalculateResponse


class PaymentsNotConfiguredError(Exception):
    """PAYMENTS_ARE_SIMULATED is off and no processor is wired."""


async def calculate_fees(
    db: AsyncSession,
    court_id: int,
    case_type_id: int,
    filing_type: str = "initial",
) -> PaymentCalculateResponse:
    result = await db.execute(
        select(CaseType, Court.court_type).join(Court).where(
            CaseType.id == case_type_id, Court.id == court_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise ValueError("Case type does not belong to this court")
    case_type, court_type = row
    additional_fees = []

    if filing_type == "service_only":
        base_fee = 0
        fee_description = "No court filing fee (service only)"
    else:
        fee_result = await db.execute(
            select(FeeSchedule).where(
                FeeSchedule.court_id == court_id,
                or_(FeeSchedule.case_type_id.is_(None), FeeSchedule.case_type_id == case_type_id),
                FeeSchedule.is_active.is_(True),
                FeeSchedule.effective_date <= datetime.now(UTC),
            )
        )
        fees = fee_result.scalars().all()
        if filing_type in ("subsequent", "motion"):
            motion_fees = [fee for fee in fees if "motion" in fee.fee_type.lower()]
            base_fee = sum(fee.amount_cents for fee in motion_fees) if motion_fees else 2000
            fee_description = "Motion filing fee"
        else:
            base_fee = case_type.filing_fee_cents
            fee_description = f"Filing fee for {case_type.name}"
            additional_fees = [
                FeeItem(
                    fee_type=fee.fee_type,
                    amount_cents=fee.amount_cents,
                    description=fee.description or fee.fee_type,
                )
                for fee in fees if "motion" not in fee.fee_type.lower()
            ]

    # Statewide electronic-filing system fee (MCL 600.1986): $25 in circuit/probate
    # civil actions, $10 in district court; not charged on appeals, motions, or
    # no-fee filings.
    is_appeal = case_type.category == CaseCategory.APPEALS
    skip_efs = filing_type in ("service_only", "subsequent", "motion") or is_appeal
    if base_fee > 0 and not skip_efs:
        efs = {
            CourtType.CIRCUIT: 2500,
            CourtType.PROBATE: 2500,
            CourtType.COURT_OF_CLAIMS: 2500,
            CourtType.DISTRICT: 1000,
        }.get(court_type, 0)
        if efs:
            additional_fees.append(FeeItem(
                fee_type="efiling_fee",
                amount_cents=efs,
                description="Electronic filing system fee (MCL 600.1986)",
            ))

    return PaymentCalculateResponse(
        filing_fee_cents=base_fee,
        additional_fees=additional_fees,
        total_cents=base_fee + sum(fee.amount_cents for fee in additional_fees),
        fee_description=fee_description,
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
    if not settings.payments_are_simulated:
        raise PaymentsNotConfiguredError(
            "Payment processing is not configured. Set PAYMENTS_ARE_SIMULATED=true "
            "only for demonstration, or wire a payment processor."
        )
    desc = f"[SIMULATED — no funds moved] {(description or '').strip()}".strip()

    payment = Payment(
        amount_cents=amount_cents,
        status=PaymentStatus.COMPLETED,  # Replace when wiring a real PSP + webhooks
        payment_method=payment_method,
        payer_id=payer_id,
        description=desc,
        transaction_ref=f"MUEFS-{uuid4().hex}",
        processed_at=datetime.now(UTC),
    )
    db.add(payment)
    await db.flush()
    return payment
