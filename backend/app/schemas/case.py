from datetime import datetime

from pydantic import BaseModel, Field

from app.models.case import CaseStatus, ParticipantRole


class CaseParticipantBase(BaseModel):
    role: ParticipantRole
    party_name: str = Field(..., max_length=255)
    attorney_bar_number: str | None = Field(None, max_length=20)
    contact_email: str | None = Field(None, max_length=255)
    contact_phone: str | None = Field(None, max_length=20)
    contact_address: str | None = Field(None, max_length=500)


class CaseParticipantCreate(CaseParticipantBase):
    user_id: int | None = None


class CaseParticipantResponse(CaseParticipantBase):
    id: int
    case_id: int
    user_id: int | None

    model_config = {"from_attributes": True}


class CaseResponse(BaseModel):
    id: int
    court_id: int
    case_number: str
    case_type_id: int
    title: str
    status: CaseStatus
    filed_date: datetime
    judge_id: int | None
    participants: list[CaseParticipantResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class CaseSearchParams(BaseModel):
    case_number: str | None = None
    party_name: str | None = None
    attorney_bar_number: str | None = None
    court_id: int | None = None
    status: CaseStatus | None = None
    page: int = 1
    page_size: int = 25


class CaseSearchResponse(BaseModel):
    cases: list[CaseResponse]
    total: int
    page: int
    page_size: int
