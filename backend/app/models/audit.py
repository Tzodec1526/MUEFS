from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, event, func
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import Session as SyncSession

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index('ix_audit_user_time', 'user_id', 'timestamp'),
        Index('ix_audit_action_time', 'action', 'timestamp'),
    )


@event.listens_for(SyncSession, "before_flush")
def _enforce_audit_log_append_only(
    session: SyncSession, flush_context: object, instances: object | None
) -> None:
    """Court compliance: audit rows are insert-only via the ORM (tamper resistance)."""
    for obj in session.deleted:
        if isinstance(obj, AuditLog):
            raise InvalidRequestError(
                "audit_log is append-only; DELETE blocked (court audit retention)."
            )
    for obj in session.dirty:
        if isinstance(obj, AuditLog):
            raise InvalidRequestError(
                "audit_log is append-only; UPDATE blocked (court audit retention)."
            )
