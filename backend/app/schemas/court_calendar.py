from datetime import date, datetime
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator


class CourtCalendarCreate(BaseModel):
    timezone: str = Field(max_length=64)
    valid_from: date
    valid_through: date
    closed_dates: dict[date, str] = Field(default_factory=dict, max_length=1096)
    authority_reference: str = Field(min_length=1, max_length=1000)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Use a valid IANA timezone, such as America/Detroit") from exc
        return value

    @field_validator("authority_reference")
    @classmethod
    def nonblank_authority(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("The calendar's approving authority or source is required")
        return value.strip()

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        if not 0 <= (self.valid_through - self.valid_from).days <= 1095:
            raise ValueError("Calendar coverage must be ordered and span no more than three years")
        for day, reason in self.closed_dates.items():
            if not self.valid_from <= day <= self.valid_through:
                raise ValueError("Every closed date must be within the covered range")
            if not reason.strip() or len(reason) > 500:
                raise ValueError("Each closure needs a reason of 1 to 500 characters")
        self.closed_dates = {day: reason.strip() for day, reason in self.closed_dates.items()}
        return self


class CourtCalendarResponse(CourtCalendarCreate):
    id: int
    court_id: int
    published_by: int
    published_at: datetime

    model_config = {"from_attributes": True}


class CourtCalendarsResponse(BaseModel):
    calendars: list[CourtCalendarResponse]
    total: int
    can_publish: bool


class FilingDateAssessment(BaseModel):
    filing_date: date | None = None
    timezone: str | None = None
    local_received_date: date | None = None
    calendar_ids: list[int] = []
    skipped_dates: dict[str, str] = {}
    error: str | None = None
