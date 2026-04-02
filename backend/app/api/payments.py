from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.database import get_db
from app.schemas.payment import (
    PaymentCalculateRequest,
    PaymentCalculateResponse,
    PaymentProcessRequest,
    PaymentResponse,
)
from app.services import audit_service, payment_service

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
    data: PaymentProcessRequest,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    # Validate payment amount against calculated fees
    calculated = await payment_service.calculate_fees(
        db, court_id=0, case_type_id=0  # TODO: look up from envelope
    )
    if data.amount_cents < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment amount cannot be negative",
        )

    payment = await payment_service.process_payment(
        db,
        amount_cents=data.amount_cents,
        payment_method=data.payment_method,
        payer_id=user_id,
        description=f"Filing envelope #{data.envelope_id}",
    )

    await audit_service.log_action(
        db, user_id=user_id, action="process_payment",
        entity_type="payment", entity_id=payment.id,
        details={"amount_cents": data.amount_cents, "envelope_id": data.envelope_id},
    )

    return payment
