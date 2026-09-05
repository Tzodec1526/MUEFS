import enum
from datetime import datetime

from sqlalchemy import DDL, DateTime, Enum, ForeignKey, Index, String, Text, event, func
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
    DISABLED = "disabled"
    BLOCKED = "blocked"
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    UNKNOWN = "unknown"
    LEGACY = "legacy"
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
        Enum(DeliveryStatus, native_enum=False, length=24), default=DeliveryStatus.DISABLED
    )
    email_recipient: Mapped[str | None] = mapped_column(String(255))
    email_sender: Mapped[str | None] = mapped_column(String(255))
    email_message_id: Mapped[str | None] = mapped_column(String(255))
    email_message: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(1000))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_notification_outbox", "delivery_status", "next_attempt_at", "id"),
        Index("ix_notification_message_id", "email_message_id", unique=True),
    )


class NotificationDeliveryEvent(Base):
    __tablename__ = "notification_delivery_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"), index=True)
    attempt_number: Mapped[int]
    outcome: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detail: Mapped[str | None] = mapped_column(String(1000))
    smtp_code: Mapped[int | None]
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # A queued event preserves the exact message, including its original recipient.
    message: Mapped[str | None] = mapped_column(Text)


for operation in ("UPDATE", "DELETE"):
    event.listen(
        NotificationDeliveryEvent.__table__,
        "after_create",
        DDL(f"""
        CREATE TRIGGER notification_delivery_events_no_{operation.lower()}
        BEFORE {operation} ON notification_delivery_events
        BEGIN SELECT RAISE(ABORT, 'notification_delivery_events is append-only'); END
    """).execute_if(dialect="sqlite"),
    )

event.listen(
    NotificationDeliveryEvent.__table__,
    "after_create",
    DDL("""
    CREATE FUNCTION protect_notification_delivery_events() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'notification_delivery_events is append-only'; END; $$
""").execute_if(dialect="postgresql"),
)
event.listen(
    NotificationDeliveryEvent.__table__,
    "after_create",
    DDL("""
    CREATE TRIGGER notification_delivery_events_append_only
    BEFORE UPDATE OR DELETE ON notification_delivery_events
    FOR EACH ROW EXECUTE FUNCTION protect_notification_delivery_events()
""").execute_if(dialect="postgresql"),
)
event.listen(
    NotificationDeliveryEvent.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS protect_notification_delivery_events()").execute_if(
        dialect="postgresql"
    ),
)
