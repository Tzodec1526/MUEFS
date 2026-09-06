from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

RecordId = Annotated[int, Field(ge=1, le=2_147_483_647)]


class SelectedServiceContact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_id: RecordId
    version: int = Field(ge=1)


class ServicePacketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_transaction_id: UUID
    document_ids: list[RecordId] = Field(min_length=1, max_length=100)
    recipients: list[SelectedServiceContact] = Field(min_length=1, max_length=100)
    reviewed: Literal[True]

    @model_validator(mode="after")
    def require_distinct_selections(self) -> Self:
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("Select each document once")
        if len({item.contact_id for item in self.recipients}) != len(self.recipients):
            raise ValueError("Select each service contact once")
        return self


class ServiceFailureReport(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    source: Literal["relay_notice", "recipient_report"]
    source_reference: str = Field(min_length=1, max_length=1000)
    description: str = Field(min_length=1, max_length=900)
    observed_at: AwareDatetime
    expected_message_id: str = Field(min_length=1, max_length=255)
    expected_attempt_count: int = Field(ge=1)
    reviewed: Literal[True]
