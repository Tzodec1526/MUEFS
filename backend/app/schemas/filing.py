from datetime import datetime

from pydantic import BaseModel

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
    case_title: str | None = None
    filing_description: str | None = None


class FilingEnvelopeUpdate(BaseModel):
    case_title: str | None = None
    filing_description: str | None = None


class FilingEnvelopeResponse(BaseModel):
    id: int
    court_id: int
    case_id: int | None
    case_type_id: int
    filer_id: int
    status: FilingStatus
    case_title: str | None
    filing_description: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    reviewer_id: int | None
    rejection_reason: str | None
    payment_id: int | None
    documents: list[FilingDocumentResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FilingListResponse(BaseModel):
    filings: list[FilingEnvelopeResponse]
    total: int
    page: int
    page_size: int


class FilingSubmitRequest(BaseModel):
    confirm: bool = True


class ClerkReviewRequest(BaseModel):
    action: str  # "accept", "reject", "return"
    reason: str | None = None


class FilingValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    missing_required_documents: list[str] = []
