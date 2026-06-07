from datetime import datetime

from pydantic import BaseModel

from app.models.case import CaseStatus, ParticipantRole


class CaseSearchParticipantPublic(BaseModel):
    """Public party/counsel identifiers only — no contact PII (court privacy)."""

    party_name: str
    role: ParticipantRole
    attorney_bar_number: str | None = None

    model_config = {"from_attributes": True}


class CaseDocketResponse(BaseModel):
    """Public docket detail with participant contact PII (email, phone, address)
    stripped — the docket is open by default, so litigant contact details are never
    served on it. Sealed-case access is gated separately."""

    id: int
    court_id: int
    case_number: str
    case_type_id: int
    title: str
    is_sealed: bool = False
    status: CaseStatus
    filed_date: datetime
    judge_id: int | None
    participants: list[CaseSearchParticipantPublic] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class CaseSearchItemResponse(BaseModel):
    """Public case search row; participant contacts omitted (court privacy)."""

    id: int
    court_id: int
    case_number: str
    case_type_id: int
    title: str
    is_sealed: bool = False
    status: CaseStatus
    filed_date: datetime
    judge_id: int | None
    created_at: datetime
    participants: list[CaseSearchParticipantPublic] = []

    model_config = {"from_attributes": True}


class CaseSearchResponse(BaseModel):
    cases: list[CaseSearchItemResponse]
    total: int
    page: int
    page_size: int
