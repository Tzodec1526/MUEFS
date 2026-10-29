from datetime import UTC, date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_serializer, field_validator

from app.models.payment import PaymentMethod, PaymentStatus
from app.schemas.common import ExpectedVersion, RecordId
from app.schemas.filing import FilingEnvelopeResponse

_SIM_PAYMENT_NOTICE = (
    "No card or ACH data is collected in this build. "
    "Payment records are simulated for workflow testing only."
)


class FeeItem(BaseModel):
    fee_type: str = Field(min_length=1, max_length=100)
    amount_cents: int = Field(ge=0, le=100_000_000)
    description: str = Field(min_length=1, max_length=1000)

    @field_validator("fee_type", "description")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A fee code and description are required")
        return value.strip()


class FilingFeeState(BaseModel):
    filing_id: int
    version: int
    payment_version: int = 0
    source: Literal["court", "waiver", "service_only", "demo", "unassessed"]
    assessment_id: str | None = None
    authority_reference: str | None = None
    items: list[FeeItem] = []
    total_cents: int | None = None
    paid_cents: int
    balance_due_cents: int | None = None
    overpaid_cents: int = 0
    review_requested_at: datetime | None
    review_reason: str | None = None
    assessment_stale: bool = False
    can_request_review: bool = False
    can_assess: bool = False
    can_pay: bool = False
    can_request_waiver: bool = False
    obligation_met: bool = False
    payments_simulated: bool
    can_manage_external_payments: bool = False
    can_record_external_payment: bool = False

    @field_serializer("review_requested_at")
    def serialize_review_time(self, value: datetime | None) -> str | None:
        return (
            value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC).isoformat() if value else None
        )


class FilingFeeDetails(FilingFeeState):
    filing: FilingEnvelopeResponse


class FeeAssessmentRequest(BaseModel):
    expected_version: ExpectedVersion
    authority_reference: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=5000)
    items: list[FeeItem] = Field(min_length=1, max_length=50)
    reviewed: Literal[True]

    @field_validator("authority_reference", "reason")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("The assessment's authority and reason are required")
        return value.strip()


class FeeReviewRequest(BaseModel):
    expected_version: ExpectedVersion
    reason: str = Field(min_length=1, max_length=2000)


class PaymentProcessRequest(BaseModel):
    envelope_id: RecordId
    expected_fee_version: ExpectedVersion
    payment_method: Literal[PaymentMethod.CREDIT_CARD, PaymentMethod.DEBIT_CARD, PaymentMethod.ACH]
    amount_cents: int = Field(gt=0)


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


class ExternalPaymentRequest(BaseModel):
    expected_fee_version: ExpectedVersion
    expected_payment_version: ExpectedVersion
    amount_cents: int = Field(gt=0, le=100_000_000)
    receipt_system: str = Field(min_length=1, max_length=120)
    receipt_reference: str = Field(min_length=1, max_length=200)
    received_at: AwareDatetime
    reason: str = Field(min_length=1, max_length=2000)
    verified: Literal[True]

    @field_validator("receipt_system", "receipt_reference", "reason")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("The source receipt and verification reason are required")
        return value.strip()


class ExternalPaymentReversal(BaseModel):
    expected_payment_version: ExpectedVersion
    reason: str = Field(min_length=1, max_length=2000)
    reviewed: Literal[True]

    @field_validator("reason")
    @classmethod
    def require_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A reason for reversing the credit is required")
        return value.strip()


class PaymentRecord(BaseModel):
    id: int
    amount_cents: int
    status: PaymentStatus
    transaction_ref: str | None
    is_simulated: bool
    external_receipt: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def serialize_created(self, value: datetime) -> str:
        return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC).isoformat()


class PaymentRecords(BaseModel):
    payments: list[PaymentRecord]
    total: int
    page: int
    payment_version: int


class PaymentActivity(BaseModel):
    event_id: str
    filing_id: int
    event_type: Literal["fee_payment_recorded", "fee_payment_reversed"]
    actor_id: int
    actor_name: str
    occurred_at: datetime
    payment_id: int
    amount_cents: int
    is_simulated: bool
    receipt_system: str
    receipt_reference: str
    received_at: AwareDatetime
    reason: str

    @field_serializer("occurred_at", "received_at")
    def serialize_time(self, value: datetime) -> str:
        return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC).isoformat()


class PaymentRegisterTotals(BaseModel):
    credits_cents: int
    reversals_cents: int


class PaymentRegister(BaseModel):
    court_id: int
    date_from: date
    date_to: date
    timezone: str
    range_start: datetime
    range_end: datetime
    generated_at: datetime
    include_simulated: bool
    total: int
    page: int
    totals: PaymentRegisterTotals
    simulated_totals: PaymentRegisterTotals
    entries: list[PaymentActivity]
