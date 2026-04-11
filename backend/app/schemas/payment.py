from datetime import datetime

from pydantic import BaseModel, Field

from app.models.payment import PaymentMethod, PaymentStatus

_SIM_PAYMENT_NOTICE = (
    "No card or ACH data is collected in this build. "
    "Payment records are simulated for workflow testing only."
)


class PaymentCalculateRequest(BaseModel):
    court_id: int
    case_type_id: int
    document_count: int = 1


class PaymentCalculateResponse(BaseModel):
    filing_fee_cents: int
    additional_fees: list[dict] = []
    total_cents: int
    fee_description: str
    is_simulated: bool = True
    simulation_notice: str = Field(default=_SIM_PAYMENT_NOTICE)


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
    is_simulated: bool = True
    simulation_notice: str = Field(default=_SIM_PAYMENT_NOTICE)

    model_config = {"from_attributes": True}
