from datetime import UTC, date, datetime

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.models.filing import FilingStatus


class FilingDocumentResponse(BaseModel):
    id: int
    document_type_code: str
    title: str
    file_size_bytes: int
    mime_type: str
    page_count: int | None
    sha256_hash: str
    is_confidential: bool
    is_text_searchable: bool
    uploaded_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("uploaded_at")
    def serialize_uploaded_at(self, value: datetime) -> str:
        return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC).isoformat()


class FilingEnvelopeCreate(BaseModel):
    court_id: int
    case_id: int | None = None  # None for new case initiation
    case_type_id: int
    filing_type: str = Field("subsequent", max_length=20)  # "initial", "subsequent", "service_only"
    case_title: str | None = Field(None, max_length=500)
    filing_description: str | None = Field(None, max_length=5000)
    fee_waiver_requested: bool = False
    fee_waiver_reason: str | None = Field(None, max_length=2000)


class FilingEnvelopeUpdate(BaseModel):
    case_title: str | None = Field(None, max_length=500)
    filing_description: str | None = Field(None, max_length=5000)
    fee_waiver_requested: bool | None = None
    fee_waiver_reason: str | None = Field(None, max_length=2000)


class FilingEnvelopeResponse(BaseModel):
    id: int
    court_id: int
    case_id: int | None
    case_type_id: int
    filer_id: int
    filing_type: str
    status: FilingStatus
    case_title: str | None
    filing_description: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    reviewer_id: int | None
    rejection_reason: str | None
    payment_id: int | None
    fee_waiver_requested: bool
    fee_waiver_granted: bool | None
    fee_waiver_reason: str | None
    fee_waiver_referred_at: datetime | None = None
    fee_waiver_decided_at: datetime | None = None
    fee_waiver_amount_due_cents: int | None = None
    cms_case_number: str | None = None
    cms_filing_id: str | None = None
    cms_error: str | None = None
    documents: list[FilingDocumentResponse] = []
    created_at: datetime
    updated_at: datetime
    submission_count: int = 0
    filing_date: date | None = None
    filing_date_basis: dict | None = None

    model_config = {"from_attributes": True}


class FilingListResponse(BaseModel):
    filings: list[FilingEnvelopeResponse]
    total: int
    page: int
    page_size: int


class CaseDocumentResponse(FilingDocumentResponse):
    copy_id: int | None = None


class CaseFilingResponse(BaseModel):
    """Docket fields only; payment references and waiver applications are private."""

    id: int
    status: FilingStatus
    case_title: str | None
    filing_description: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    documents: list[CaseDocumentResponse]
    created_at: datetime
    filing_date: date | None = None

    model_config = {"from_attributes": True}

class MyFilingsResponse(FilingListResponse):
    status_counts: dict[FilingStatus, int]
    court_names: dict[int, str]


class ClerkReviewRequest(BaseModel):
    action: str  # "accept", "reject", "return"
    expected_submission_count: int = Field(..., ge=0, strict=True)
    reason: str | None = Field(None, max_length=5000)


class BatchReviewItem(BaseModel):
    filing_id: int = Field(..., ge=1, strict=True)
    expected_submission_count: int = Field(..., ge=0, strict=True)


class BatchReviewRequest(BaseModel):
    """Batch accept support (reject/return require per-filing reasons so are single only)."""
    filings: list[BatchReviewItem] = Field(..., min_length=1, max_length=100)
    action: str  # currently only "accept" supported for batch

    @field_validator("filings")
    @classmethod
    def unique_filings(cls, filings: list[BatchReviewItem]) -> list[BatchReviewItem]:
        if len({item.filing_id for item in filings}) != len(filings):
            raise ValueError("A filing may appear only once per review batch")
        return filings


class FilingValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    missing_required_documents: list[str] = []


class FilingTransactionResponse(BaseModel):
    id: str
    submission_number: int
    event_type: str
    actor_name: str
    occurred_at: datetime
    details: dict

    model_config = {"from_attributes": True}

    @field_serializer("occurred_at")
    def serialize_occurred_at(self, value: datetime) -> str:
        return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC).isoformat()


class FeeWaiverState(BaseModel):
    granted: bool | None
    referred_at: datetime | None
    decided_at: datetime | None
    amount_due_cents: int | None
    balance_due_cents: int | None = None
    fee_version: int = 0
    can_pay: bool
    allowed_actions: list[str]
    payments_simulated: bool


class FilingHistoryResponse(BaseModel):
    filing_id: int
    status: FilingStatus
    submission_count: int
    transactions: list[FilingTransactionResponse]
    total: int
    page: int
    page_size: int
    fee_waiver: FeeWaiverState | None = None
    filing_date: date | None = None
    filing_date_basis: dict | None = None
    court_id: int
    can_manage_documents: bool = False
