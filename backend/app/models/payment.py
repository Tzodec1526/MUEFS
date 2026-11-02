import enum
from datetime import datetime

from sqlalchemy import (
    DDL,
    JSON,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    event,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime


class PaymentStatus(enum.StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    WAIVED = "waived"
    REVERSED = "reversed"


class PaymentMethod(enum.StrEnum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    ACH = "ach"
    WAIVER = "waiver"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    envelope_id: Mapped[int | None] = mapped_column(ForeignKey(
        "filing_envelopes.id", use_alter=True, name="fk_payment_envelope",
    ), index=True)
    fee_basis: Mapped[dict | None] = mapped_column(JSON)
    external_request_key: Mapped[str | None] = mapped_column(String(36))
    external_receipt_key: Mapped[str | None] = mapped_column(String(64))
    external_receipt: Mapped[dict | None] = mapped_column(JSON)
    is_simulated: Mapped[bool] = mapped_column(default=True, server_default=true())
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.PENDING
    )
    payment_method: Mapped[PaymentMethod | None] = mapped_column(Enum(PaymentMethod))
    transaction_ref: Mapped[str | None] = mapped_column(String(255))
    payer_id: Mapped[int | None] = mapped_column()
    description: Mapped[str | None] = mapped_column(String(500))
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )

    __table_args__ = (
        Index("uq_payment_external_request", "external_request_key", unique=True,
              postgresql_where=text("external_request_key IS NOT NULL"),
              sqlite_where=text("external_request_key IS NOT NULL")),
        Index("uq_payment_external_receipt", "external_receipt_key", unique=True,
              postgresql_where=text("status = 'COMPLETED' AND external_receipt_key IS NOT NULL"),
              sqlite_where=text("status = 'COMPLETED' AND external_receipt_key IS NOT NULL")),
    )


_unchanged = " AND ".join(f"NEW.{column.name} IS OLD.{column.name}"
                          for column in Payment.__table__.columns if column.name != "status")
event.listen(Payment.__table__, "after_create", DDL(f"""
    CREATE TRIGGER payments_external_no_update BEFORE UPDATE ON payments
    WHEN OLD.external_request_key IS NOT NULL AND NOT (
        OLD.status = 'COMPLETED' AND NEW.status = 'REVERSED' AND {_unchanged})
    BEGIN SELECT RAISE(ABORT, 'External payment evidence is retained'); END
""").execute_if(dialect="sqlite"))
event.listen(Payment.__table__, "after_create", DDL("""
    CREATE TRIGGER payments_external_no_delete BEFORE DELETE ON payments
    WHEN OLD.external_request_key IS NOT NULL
    BEGIN SELECT RAISE(ABORT, 'External payment evidence is retained'); END
""").execute_if(dialect="sqlite"))
event.listen(Payment.__table__, "after_create", DDL("""
    CREATE FUNCTION protect_external_payments() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.external_request_key IS NOT NULL THEN
            IF TG_OP = 'UPDATE' AND OLD.status = 'COMPLETED' AND NEW.status = 'REVERSED'
                AND (to_jsonb(NEW) - 'status') = (to_jsonb(OLD) - 'status') THEN RETURN NEW; END IF;
            RAISE EXCEPTION 'External payment evidence is retained';
        END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END; $$
""").execute_if(dialect="postgresql"))
event.listen(Payment.__table__, "after_create", DDL("""
    CREATE TRIGGER payments_external_retained BEFORE UPDATE OR DELETE ON payments
    FOR EACH ROW EXECUTE FUNCTION protect_external_payments()
""").execute_if(dialect="postgresql"))
event.listen(Payment.__table__, "after_drop", DDL(
    "DROP FUNCTION IF EXISTS protect_external_payments()"
).execute_if(dialect="postgresql"))
