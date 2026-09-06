"""Retained document packages and their explicitly selected recipients."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.retention import append_only


class ServicePacket(Base):
    __tablename__ = "service_packets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    filing_id: Mapped[int] = mapped_column(ForeignKey("filing_envelopes.id"))
    source_transaction_id: Mapped[str] = mapped_column(ForeignKey("filing_transactions.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(36))
    request_sha256: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_service_packet_key"),
        Index("ix_service_packets_filing", "filing_id", "created_at", "id"),
        Index("ix_service_packets_case", "case_id", "created_at", "id"),
    )


class ServiceRecipient(Base):
    __tablename__ = "service_recipients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    packet_id: Mapped[str] = mapped_column(ForeignKey("service_packets.id"))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("service_contacts.id"))
    contact_version: Mapped[int]
    contact_snapshot: Mapped[dict] = mapped_column(JSON)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"), unique=True)

    __table_args__ = (
        UniqueConstraint("packet_id", "recipient_id", name="uq_service_packet_recipient"),
    )


class ServiceEvent(Base):
    __tablename__ = "service_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_recipient_id: Mapped[str] = mapped_column(ForeignKey("service_recipients.id"))
    action: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict] = mapped_column(JSON)

    __table_args__ = (Index("ix_service_events_recipient", "service_recipient_id", "id"),)


append_only(ServicePacket.__table__)
append_only(ServiceRecipient.__table__)
append_only(ServiceEvent.__table__)
