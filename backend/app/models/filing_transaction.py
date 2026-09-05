"""Retained filing transactions. Submission details are snapshots, not live references."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DDL, JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


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
        UniqueConstraint("filing_id", "idempotency_key", name="uq_filing_submission_key"),
    )


# Protect retained transactions from UPDATE/DELETE, including SQL outside the ORM.
# Database owners can remove these guards; production retention still needs restricted
# database roles, backups, and the court's approved retention policy.
for operation in ("UPDATE", "DELETE"):
    event.listen(FilingTransaction.__table__, "after_create", DDL(f"""
        CREATE TRIGGER filing_transactions_no_{operation.lower()}
        BEFORE {operation} ON filing_transactions
        BEGIN SELECT RAISE(ABORT, 'filing_transactions is append-only'); END
    """).execute_if(dialect="sqlite"))

event.listen(FilingTransaction.__table__, "after_create", DDL("""
    CREATE FUNCTION protect_filing_transactions() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'filing_transactions is append-only'; END; $$
""").execute_if(dialect="postgresql"))
event.listen(FilingTransaction.__table__, "after_create", DDL("""
    CREATE TRIGGER filing_transactions_append_only BEFORE UPDATE OR DELETE
    ON filing_transactions FOR EACH ROW EXECUTE FUNCTION protect_filing_transactions()
""").execute_if(dialect="postgresql"))
event.listen(FilingTransaction.__table__, "after_drop", DDL(
    "DROP FUNCTION IF EXISTS protect_filing_transactions()"
).execute_if(dialect="postgresql"))
