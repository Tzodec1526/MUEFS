from datetime import datetime

from pydantic import BaseModel

from app.models.payment import PaymentMethod, PaymentStatus


class PaymentCalculateRequest(BaseModel):
    court_id: int
    case_type_id: int
    document_count: int = 1


class PaymentCalculateResponse(BaseModel):
    filing_fee_cents: int
    additional_fees: list[dict] = []
    total_cents: int
    fee_description: str


class PaymentProcessRequest(BaseModel):
    envelope_id: int
    payment_method: PaymentMethod
    amount_cents: int


class PaymentResponse(BaseModel):
    id: int
    amount_cents: int
    status: PaymentStatus
    payment_method: PaymentMethod | None
    transaction_ref: str | None
    processed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
