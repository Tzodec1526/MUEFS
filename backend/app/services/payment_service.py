from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.court import CaseCategory, CaseType, Court, CourtType, FeeSchedule
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.schemas.payment import PaymentCalculateResponse


async def calculate_fees(
    db: AsyncSession,
    court_id: int,
    case_type_id: int,
    document_count: int = 1,
    filing_type: str = "initial",
) -> PaymentCalculateResponse:
    # Get base filing fee from case type
    result = await db.execute(
        select(CaseType).where(CaseType.id == case_type_id)
    )
    case_type = result.scalar_one_or_none()

    if filing_type == "service_only":
        base_fee = 0
        fee_description = "No court filing fee (service only)"
    elif filing_type in ("subsequent", "motion"):
        # Prefer motion fee from FeeSchedule if seeded (more natural, per-court)
        motion_fee_result = await db.execute(
            select(FeeSchedule).where(
                FeeSchedule.court_id == court_id,
                FeeSchedule.fee_type.ilike("%motion%"),
                FeeSchedule.is_active == True,  # noqa: E712
            )
        )
        motion_fees = motion_fee_result.scalars().all()
        if motion_fees:
            base_fee = sum(f.amount_cents for f in motion_fees)
            fee_description = "Motion filing fee"
        else:
            # Fallback for demo if no schedule (e.g. $20)
            base_fee = 2000
            fee_description = "Motion filing fee"
    else:
        base_fee = case_type.filing_fee_cents if case_type else 0
        fee_description = f"Filing fee for {case_type.name}" if case_type else "Filing fee"

    # Get additional fees from fee schedule (skip the motion base if used for subsequent)
    fee_result = await db.execute(
        select(FeeSchedule).where(
            FeeSchedule.court_id == court_id,
            FeeSchedule.is_active == True,  # noqa: E712
        )
    )
    additional_fees = []
    extra_total = 0
    for fee in fee_result.scalars().all():
        is_motion_fee = "motion" in (fee.fee_type or "").lower()
        # Motion fees are folded into base_fee for motions and excluded for initial
        # filings, so never list them here; for motions, non-motion add-ons don't apply.
        if is_motion_fee or filing_type in ("subsequent", "motion"):
            continue
        additional_fees.append({
            "fee_type": fee.fee_type,
            "amount_cents": fee.amount_cents,
            "description": fee.description or fee.fee_type,
        })
        extra_total += fee.amount_cents

    # Statewide electronic-filing system fee (MCL 600.1986): $25 in circuit/probate
    # civil actions, $10 in district court; not charged on appeals, motions, or
    # no-fee filings.
    is_appeal = case_type is not None and case_type.category == CaseCategory.APPEALS
    skip_efs = filing_type in ("service_only", "subsequent", "motion") or is_appeal
    if base_fee > 0 and not skip_efs:
        court_result = await db.execute(select(Court).where(Court.id == court_id))
        court = court_result.scalar_one_or_none()
        efs = 0
        if court is not None:
            if court.court_type in (
                CourtType.CIRCUIT, CourtType.PROBATE, CourtType.COURT_OF_CLAIMS,
            ):
                efs = 2500
            elif court.court_type == CourtType.DISTRICT:
                efs = 1000
        if efs:
            additional_fees.append({
                "fee_type": "efiling_fee",
                "amount_cents": efs,
                "description": "Electronic filing system fee (MCL 600.1986)",
            })
            extra_total += efs

    total = base_fee + extra_total

    return PaymentCalculateResponse(
        filing_fee_cents=base_fee,
        additional_fees=additional_fees,
        total_cents=total,
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
