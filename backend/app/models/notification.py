import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NotificationType(enum.StrEnum):
    FILING_SUBMITTED = "filing_submitted"
    FILING_ACCEPTED = "filing_accepted"
    FILING_REJECTED = "filing_rejected"
    FILING_RETURNED = "filing_returned"
    SERVICE_OF_PROCESS = "service_of_process"
    CASE_UPDATE = "case_update"


class DeliveryStatus(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class ServiceMethod(enum.StrEnum):
    ELECTRONIC = "electronic"
    MAIL = "mail"
    HAND_DELIVERY = "hand_delivery"


class ServiceContact(Base):
    __tablename__ = "service_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    method: Mapped[ServiceMethod] = mapped_column(
        Enum(ServiceMethod), default=ServiceMethod.ELECTRONIC
    )
    address: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_type: Mapped[NotificationType] = mapped_column(Enum(NotificationType))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    filing_envelope_id: Mapped[int | None] = mapped_column(
        ForeignKey("filing_envelopes.id"), index=True
    )
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus), default=DeliveryStatus.PENDING
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
