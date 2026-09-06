import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PaymentStatus(enum.StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    WAIVED = "waived"


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
    is_simulated: Mapped[bool] = mapped_column(default=True, server_default=true())
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.PENDING
    )
    payment_method: Mapped[PaymentMethod | None] = mapped_column(Enum(PaymentMethod))
    transaction_ref: Mapped[str | None] = mapped_column(String(255))
    payer_id: Mapped[int | None] = mapped_column()
    description: Mapped[str | None] = mapped_column(String(500))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
