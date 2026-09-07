"""Retained filing transactions. Submission details are snapshots, not live references."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.retention import append_only


class FilingTransaction(Base):
    __tablename__ = "filing_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    filing_id: Mapped[int] = mapped_column(ForeignKey("filing_envelopes.id"))
    submission_number: Mapped[int] = mapped_column()
    event_type: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict] = mapped_column(JSON)
    idempotency_key: Mapped[str | None] = mapped_column(String(36))

    __table_args__ = (
        Index("ix_filing_transactions_history", "filing_id", "occurred_at", "id"),
        Index(
            "ix_filing_payment_activity", "occurred_at", "filing_id", "id",
            postgresql_where=text("event_type IN ('fee_payment_recorded', 'fee_payment_reversed')"),
            sqlite_where=text("event_type IN ('fee_payment_recorded', 'fee_payment_reversed')"),
        ),
        UniqueConstraint("filing_id", "idempotency_key", name="uq_filing_submission_key"),
    )


append_only(FilingTransaction.__table__)
