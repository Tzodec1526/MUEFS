from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models.case import ParticipantRole
from app.models.notification import DeliveryStatus, ServiceMethod
from app.schemas.common import MAX_RECORD_ID, RecordId
from app.schemas.filing import FilingDocumentResponse


class SelectedServiceContact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_id: RecordId
    version: int = Field(ge=1, le=MAX_RECORD_ID)


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


class DeliveryRecipientOption(BaseModel):
    participant_id: int
    name: str
    role: ParticipantRole
    represented_party_name: str | None
    contact_id: int | None
    version: int | None
    method: ServiceMethod | None
    email: str | None
    address: str | None
    authority: str | None
    issues: list[str]


class DeliveryOptions(BaseModel):
    enabled: bool
    source_transaction_id: str
    case_number: str
    case_title: str
    court_name: str | None
    documents: list[FilingDocumentResponse]
    recipients: list[DeliveryRecipientOption]
    total: int
    page_size: int


class DeliveryCreated(BaseModel):
    packet_id: str


class ReceivedDelivery(BaseModel):
    id: str
    actor_name: str
    created_at: datetime
    delivery_status: DeliveryStatus


class ReceivedDeliveries(BaseModel):
    deliveries: list[ReceivedDelivery]
    total: int
    page_size: int


class SentDelivery(BaseModel):
    id: str
    packet_id: str
    name: str | None
    email: str | None
    created_at: datetime
    delivery_status: DeliveryStatus


class SentDeliveries(BaseModel):
    deliveries: list[SentDelivery]
    total: int
    page_size: int


class DeliveryDetails(BaseModel):
    id: str
    packet_id: str
    filing_id: int
    source_transaction_id: str
    sender: str
    created_at: datetime
    court_name: str | None
    case_number: str
    case_title: str
    documents: list[FilingDocumentResponse]
    contact: dict
    delivery_status: DeliveryStatus
    last_error: str | None
    message_id: str | None
    attempt_count: int
    can_report_failure: bool
    acknowledged_at: datetime | None
    can_acknowledge: bool
    can_retry: bool


class PortalDeliveryEvent(BaseModel):
    id: int
    action: str
    occurred_at: datetime
    actor_name: str
    details: dict


class EmailDeliveryEvent(BaseModel):
    id: int
    action: str
    occurred_at: datetime
    detail: str | None
    smtp_code: int | None
    attempt_number: int


class DeliveryEvents(BaseModel):
    events: list[PortalDeliveryEvent] | list[EmailDeliveryEvent]
    total: int
    page_size: int


class DeliveryAcknowledged(BaseModel):
    acknowledged: bool


class DeliveryRetryQueued(BaseModel):
    delivery_status: DeliveryStatus


class DeliveryFailureRecorded(BaseModel):
    report_id: int
    delivery_status: DeliveryStatus
