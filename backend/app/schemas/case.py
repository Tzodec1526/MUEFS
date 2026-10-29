from datetime import UTC, date, datetime

from pydantic import AliasPath, BaseModel, Field, field_serializer

from app.models.case import CaseStatus, ParticipantRole


class CaseSearchParticipantPublic(BaseModel):
    """Public party/counsel identifiers only — no contact PII (court privacy)."""

    id: int
    party_name: str
    role: ParticipantRole
    attorney_bar_number: str | None = None
    represented_party_name: str | None = None
    is_active: bool = True

    model_config = {"from_attributes": True}


class CasePublicRecord(BaseModel):
    """Public docket and search fields with participant contact PII (email, phone, address)
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
    filing_date: date | None = None
    judge_id: int | None
    participants: list[CaseSearchParticipantPublic] = []
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("filed_date", "created_at")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC).isoformat()


class CaseDocketResponse(CasePublicRecord):
    """One case, with what the current account may do on it."""

    can_manage_records: bool = False
    can_file: bool = False


class CaseSearchResult(CasePublicRecord):
    court_name: str = Field(validation_alias=AliasPath("court", "name"))
    court_county: str = Field(validation_alias=AliasPath("court", "county"))


class CaseSearchResponse(BaseModel):
    cases: list[CaseSearchResult]
    total: int
    page: int
    page_size: int
