from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.config import settings
from app.database import get_db
from app.schemas.payment import (
    PaymentCalculateRequest,
    PaymentCalculateResponse,
    PaymentProcessRequest,
    PaymentResponse,
)
from app.services import audit_service, filing_service, payment_service
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/calculate", response_model=PaymentCalculateResponse)
async def calculate_fees(
    data: PaymentCalculateRequest,
    db: AsyncSession = Depends(get_db),
    _user_id: int = Depends(get_current_user_id),
):
    return await payment_service.calculate_fees(
        db, data.court_id, data.case_type_id, data.document_count
    )


@router.post("/process", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def process_payment(
    request: Request,
    data: PaymentProcessRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    if data.amount_cents <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount must be positive",
        )

    # Look up the filing envelope to validate payment against actual fees
    filing = await filing_service.get_filing(db, data.envelope_id)
    if not filing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Filing envelope not found",
        )
    if filing.filer_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to pay for this filing",
        )

    # Prevent double-payment
    if filing.payment_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment already processed for this filing",
        )

    # Validate amount matches calculated fees
    calculated = await payment_service.calculate_fees(
        db, court_id=filing.court_id, case_type_id=filing.case_type_id
    )
    if data.amount_cents != calculated.total_cents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Payment amount ({data.amount_cents}) does not match "
                f"calculated fee ({calculated.total_cents})"
            ),
        )

    payment = await payment_service.process_payment(
        db,
        amount_cents=data.amount_cents,
        payment_method=data.payment_method,
        payer_id=user_id,
        description=f"Filing envelope #{data.envelope_id}",
    )

    # Link payment to filing
    filing.payment_id = payment.id
    await db.flush()

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

    return PaymentResponse.model_validate(
        payment,
        from_attributes=True,
    ).model_copy(
        update={
            "is_simulated": settings.payments_are_simulated,
            "simulation_notice": (
                "No card or ACH data is collected in this build. "
                "This transaction is recorded for workflow testing only."
                if settings.payments_are_simulated
                else ""
            ),
        },
    )
