from datetime import datetime

from pydantic import BaseModel, Field

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
    documents: list[FilingDocumentResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FilingListResponse(BaseModel):
    filings: list[FilingEnvelopeResponse]
    total: int
    page: int
    page_size: int


class ClerkReviewRequest(BaseModel):
    action: str  # "accept", "reject", "return"
    reason: str | None = Field(None, max_length=5000)


class FilingValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    missing_required_documents: list[str] = []
