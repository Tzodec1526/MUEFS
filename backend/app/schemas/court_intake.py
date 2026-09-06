from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class IntakeCaseTypeChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    is_active: StrictBool


class IntakeCaseType(IntakeCaseTypeChange):
    code: str
    name: str


class CourtIntakeState(BaseModel):
    court_id: int
    court_name: str
    version: int
    is_efiling_enabled: bool
    public_notice: str | None
    case_types: list[IntakeCaseType]


class CourtIntakeResponse(CourtIntakeState):
    can_manage: bool


class CourtIntakeChange(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    expected_version: int = Field(ge=0)
    is_efiling_enabled: StrictBool
    public_notice: str | None = Field(max_length=2000)
    case_types: list[IntakeCaseTypeChange] = Field(max_length=500)
    reason: str = Field(min_length=1, max_length=2000)
    authority_reference: str = Field(min_length=1, max_length=300)

    @field_validator("public_notice")
    @classmethod
    def blank_notice(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("case_types")
    @classmethod
    def unique_case_types(cls, value: list[IntakeCaseTypeChange]) -> list[IntakeCaseTypeChange]:
        if len({item.id for item in value}) != len(value):
            raise ValueError("Each case type must appear exactly once")
        return value


class CourtIntakeHistoryEntry(BaseModel):
    id: int
    timestamp: datetime
    actor_name: str
    reason: str
    authority_reference: str
    before: CourtIntakeState
    after: CourtIntakeState


class CourtIntakeHistory(BaseModel):
    changes: list[CourtIntakeHistoryEntry]
    total: int
