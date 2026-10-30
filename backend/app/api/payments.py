from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import lock_current_user, require_user_may_manage_efilings
from app.database import get_db
from app.models.user import User
from app.schemas.payment import (
    PaymentProcessRequest,
    PaymentResponse,
)
from app.services import audit_service, filing_service, payment_service
from app.services.fee_assessment_service import fee_state
from app.services.filing_record_service import record_transaction
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/process", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def process_payment(
    request: Request,
    data: PaymentProcessRequest,
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(require_user_may_manage_efilings),
):
    user_id = current_user.id
    await require_user_may_manage_efilings(await lock_current_user(db, user_id))
    filing = await filing_service.get_filing(db, data.envelope_id, for_update=True)
    if not filing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Filing not found",
        )
    if filing.filer_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to pay for this filing",
        )

    fees = await fee_state(db, filing, user_id)
    if fees.version != data.expected_fee_version:
        raise HTTPException(409, "The fee record changed. Refresh and review it before payment")
    if fees.balance_due_cents is None:
        raise HTTPException(409, "A current court fee assessment is required before payment")
    if not fees.can_pay:
        raise HTTPException(409, "This filing is not awaiting payment")
    expected_cents = fees.balance_due_cents
    if data.amount_cents != expected_cents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Payment amount ({data.amount_cents}) does not match amount due ({expected_cents})"
            ),
        )

    basis = {
        "source": fees.source,
        "assessment_id": fees.assessment_id,
        "version": fees.version,
        "authority_reference": fees.authority_reference,
        "items": [item.model_dump() for item in fees.items],
        "total_cents": fees.total_cents,
        "previous_paid_cents": fees.paid_cents,
    }
    try:
        payment = await payment_service.process_payment(
            db,
            amount_cents=data.amount_cents,
            payment_method=data.payment_method,
            payer_id=user_id,
            envelope_id=filing.id,
            fee_basis=basis,
            description=f"Filing #{data.envelope_id}",
        )
    except payment_service.PaymentsNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    # Keep the legacy latest-payment pointer; the balance uses all completed payments.
    filing.payment_id = payment.id
    filing.payment_version += 1
    await db.flush()
    await record_transaction(
        db,
        filing,
        "payment_recorded",
        user_id,
        details={
            "payment": {
                "id": payment.id,
                "amount_cents": payment.amount_cents,
                "transaction_ref": payment.transaction_ref,
                "is_simulated": payment.is_simulated,
                "fee_basis": basis,
            },
        },
    )

    await audit_service.log_action(
        db,
        user_id=user_id,
        action="process_payment",
        entity_type="payment",
        entity_id=payment.id,
        details={"amount_cents": data.amount_cents, "envelope_id": data.envelope_id},
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )

    return PaymentResponse.model_validate(payment)
