from datetime import datetime

from pydantic import BaseModel

from app.models.court import CaseCategory, CourtType


class CourtBase(BaseModel):
    name: str
    county: str
    court_type: CourtType
    division: str | None = None
    address: str | None = None
    city: str | None = None
    zip_code: str | None = None
    phone: str | None = None


class CourtResponse(CourtBase):
    id: int
    state: str
    cms_type: str | None
    is_efiling_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CourtListResponse(BaseModel):
    courts: list[CourtResponse]
    total: int


class CaseTypeBase(BaseModel):
    code: str
    name: str
    category: CaseCategory
    filing_fee_cents: int = 0
    description: str | None = None


class CaseTypeResponse(CaseTypeBase):
    id: int
    court_id: int
    is_active: bool

    model_config = {"from_attributes": True}


class FilingRequirementResponse(BaseModel):
    id: int
    document_type_code: str
    is_required: bool
    description: str
    mcr_reference: str | None
    local_rule_reference: str | None
    page_limit: int | None
    format_notes: str | None

    model_config = {"from_attributes": True}


class FilingChecklistResponse(BaseModel):
    id: int
    motion_type: str
    checklist_items: dict
    help_text: str | None
    mcr_url: str | None

    model_config = {"from_attributes": True}


class FeeScheduleResponse(BaseModel):
    id: int
    fee_type: str
    amount_cents: int
    description: str | None
    effective_date: datetime

    model_config = {"from_attributes": True}
