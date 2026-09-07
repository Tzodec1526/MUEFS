"""Resolve the current court assessment, waiver decision and recorded payment balance."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.court import CaseType
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.payment import Payment, PaymentStatus
from app.models.user import User, UserType
from app.schemas.payment import FeeItem, FilingFeeState
from app.services import access_service


async def fee_state(
    db: AsyncSession,
    filing: FilingEnvelope,
    user_id: int | None = None,
) -> FilingFeeState:
    query = select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
        Payment.envelope_id == filing.id,
        Payment.status == PaymentStatus.COMPLETED,
        Payment.payer_id == filing.filer_id,
        Payment.amount_cents > 0,
    )
    if not settings.allow_demo_mode:
        query = query.where(Payment.is_simulated.is_(False))
    paid = await db.scalar(query) or 0
    assessment = (
        await db.scalar(
            select(FilingTransaction).where(
                FilingTransaction.id == filing.fee_assessment_id,
                FilingTransaction.filing_id == filing.id,
                FilingTransaction.event_type == "fee_assessed",
            )
        )
        if filing.fee_assessment_id
        else None
    )
    result = FilingFeeState(
        filing_id=filing.id,
        version=filing.fee_version,
        payment_version=filing.payment_version,
        source="unassessed",
        paid_cents=paid,
        review_requested_at=filing.fee_review_requested_at,
        payments_simulated=settings.payments_are_simulated and settings.allow_demo_mode,
        assessment_stale=filing.fee_assessment_id is not None
        and (assessment is None or assessment.details.get("filing_version") != filing.fee_version),
        assessment_id=assessment.id if assessment else None,
    )
    if filing.fee_review_requested_at is not None:
        review_details = await db.scalar(
            select(FilingTransaction.details)
            .where(
                FilingTransaction.filing_id == filing.id,
                FilingTransaction.event_type == "fee_review_requested",
            )
            .order_by(FilingTransaction.occurred_at.desc(), FilingTransaction.id.desc())
            .limit(1)
        )
        result.review_reason = review_details.get("reason") if review_details else None
    if filing.filing_type == "service_only":
        result.source, result.total_cents = "service_only", 0
    elif filing.fee_waiver_granted is True:
        result.source, result.total_cents = "waiver", 0
    elif filing.fee_waiver_granted is False and filing.fee_waiver_amount_due_cents is not None:
        result.source, result.total_cents = "waiver", filing.fee_waiver_amount_due_cents
        result.items = [
            FeeItem(
                fee_type="waiver_decision",
                amount_cents=result.total_cents,
                description="Amount due under the signed fee waiver decision",
            )
        ]
    elif assessment is not None and not result.assessment_stale:
        result.source, result.total_cents = "court", assessment.details["total_cents"]
        result.authority_reference = assessment.details["authority_reference"]
        result.items = [FeeItem.model_validate(item) for item in assessment.details["items"]]
    elif (
        filing.fee_assessment_id is None
        and settings.allow_demo_mode
        and not filing.fee_review_requested_at
    ):
        # These are visibly synthetic examples, never a substitute for a court assessment.
        # A subsequent filing is not necessarily a motion. Do not invent a $20 charge.
        case_type = await db.get(CaseType, filing.case_type_id)
        if case_type is not None and (
            filing.filing_type == "initial" or case_type.filing_fee_cents == 0
        ):
            result.source, result.total_cents = "demo", case_type.filing_fee_cents
            result.items = [
                FeeItem(
                    fee_type="demo_example",
                    amount_cents=result.total_cents,
                    description="Synthetic example amount — not court assessed",
                )
            ]
    if result.source in ("waiver", "service_only"):
        result.assessment_id = None
        result.assessment_stale = False
    if result.total_cents is not None:
        result.balance_due_cents = max(0, result.total_cents - paid)
        result.overpaid_cents = max(0, paid - result.total_cents)
    result.obligation_met = result.balance_due_cents == 0 or (
        filing.fee_waiver_requested and filing.fee_waiver_granted is None
    )
    owner = await db.get(User, user_id) if user_id == filing.filer_id else None
    can_manage = owner is not None and owner.is_active and owner.user_type != UserType.PUBLIC
    reviewable = (
        filing.filing_type != "service_only"
        and filing.status not in (FilingStatus.REJECTED, FilingStatus.SERVED)
        and not filing.fee_waiver_requested
        and filing.fee_waiver_granted is None
    )
    result.can_request_review = reviewable and can_manage and filing.fee_review_requested_at is None
    result.can_assess = (
        reviewable
        and user_id != filing.filer_id
        and await access_service.user_is_court_staff_for_court(
            db,
            user_id,
            filing.court_id,
        )
    )
    result.can_pay = (
        can_manage
        and (result.balance_due_cents or 0) > 0
        and filing.status not in (FilingStatus.REJECTED, FilingStatus.SERVED)
        and not (filing.fee_waiver_requested and filing.fee_waiver_granted is None)
    )
    result.can_manage_external_payments = bool(
        settings.external_payments_enabled and user_id is not None and user_id != filing.filer_id
        and await access_service.user_has_court_administrator_assignment(
            db, user_id, filing.court_id,
        )
    )
    result.can_record_external_payment = (
        result.can_manage_external_payments and result.source in ("court", "waiver")
        and (result.balance_due_cents or 0) > 0
        and filing.status not in (FilingStatus.REJECTED, FilingStatus.SERVED)
        and not (filing.fee_waiver_requested and filing.fee_waiver_granted is None)
    )
    result.can_request_waiver = (
        can_manage
        and filing.submitted_at is None
        and filing.fee_waiver_granted is None
        and filing.filing_type != "service_only"
        and filing.status == FilingStatus.DRAFT
    )
    return result
