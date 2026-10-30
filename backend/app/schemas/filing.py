from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.filing import FilingStatus, FilingType
from app.schemas.common import MAX_RECORD_ID, RecordId


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


class FilingEnvelopeCreate(BaseModel):
    court_id: RecordId
    case_id: RecordId | None = None
    case_type_id: RecordId
    filing_type: FilingType = FilingType.SUBSEQUENT
    case_title: str | None = Field(None, max_length=500)
    filing_description: str | None = Field(None, max_length=5000)
    fee_waiver_requested: bool = False
    fee_waiver_reason: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def require_matching_case_reference(self) -> Self:
        if self.filing_type == FilingType.INITIAL and self.case_id is not None:
            raise ValueError(
                "An initial filing opens a new case and cannot reference an existing case"
            )
        if self.filing_type != FilingType.INITIAL and self.case_id is None:
            raise ValueError("A subsequent or service-only filing must reference an existing case")
        return self


class FilingEnvelopeUpdate(BaseModel):
    expected_details_token: str | None = Field(None, pattern=r"^[0-9a-f]{64}$")
    case_title: str | None = Field(None, max_length=500)
    filing_description: str | None = Field(None, max_length=5000)
    fee_waiver_requested: bool | None = None
    fee_waiver_reason: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def require_details_token(self) -> Self:
        editing = (
            self.case_title is not None
            or self.filing_description is not None
            or self.fee_waiver_requested is not None
            or self.fee_waiver_reason is not None
        )
        if editing and not self.expected_details_token:
            raise ValueError("Load the filing's current details before editing them")
        return self


class FilingSubmitRequest(BaseModel):
    expected_submission_token: str = Field(pattern=r"^[0-9a-f]{64}$")


class FilingEnvelopeResponse(BaseModel):
    submission_token: str
    details_token: str
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


class FilingSummary(BaseModel):
    """Fields used by filing lists; documents and private details load on opening."""

    id: int
    court_id: int
    case_id: int | None
    filer_id: int
    status: FilingStatus
    case_title: str | None
    filing_description: str | None
    submitted_at: datetime | None
    rejection_reason: str | None
    fee_waiver_requested: bool
    fee_waiver_granted: bool | None
    created_at: datetime
    updated_at: datetime
    submission_count: int
    document_count: int

    model_config = {"from_attributes": True}


class FilingListResponse(BaseModel):
    filings: list[FilingSummary]
    total: int
    page: int
    page_size: int


class ClerkQueueResponse(FilingListResponse):
    submitted_count: int
    under_review_count: int
    waiting_48h: int
    oldest_submitted_at: datetime | None
    as_of: datetime


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
    action: Literal["accept", "reject", "return"]
    expected_submission_count: int = Field(..., ge=0, strict=True)
    reason: str | None = Field(None, max_length=5000)


class BatchReviewItem(BaseModel):
    filing_id: int = Field(..., ge=1, le=MAX_RECORD_ID, strict=True)
    expected_submission_count: int = Field(..., ge=0, strict=True)


class BatchReviewRequest(BaseModel):
    """Batch accept support (reject/return require per-filing reasons so are single only)."""
    filings: list[BatchReviewItem] = Field(..., min_length=1, max_length=100)
    action: Literal["accept"]

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
