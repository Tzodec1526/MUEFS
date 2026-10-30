from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.payment import Payment, PaymentMethod, PaymentStatus


class PaymentsNotConfiguredError(Exception):
    """PAYMENTS_ARE_SIMULATED is off and no processor is wired."""
    pass


async def process_payment(
    db: AsyncSession,
    amount_cents: int,
    payment_method: PaymentMethod,
    payer_id: int,
    envelope_id: int,
    fee_basis: dict,
    description: str | None = None,
) -> Payment:
    if not settings.payments_are_simulated or not settings.allow_demo_mode:
        raise PaymentsNotConfiguredError(
            "Payment processing is not configured. Set PAYMENTS_ARE_SIMULATED=true "
            "only for demonstration, or wire a payment processor."
        )
    desc = f"[SIMULATED: no funds moved] {(description or '').strip()}".strip()

    payment = Payment(
        envelope_id=envelope_id,
        fee_basis=fee_basis,
        amount_cents=amount_cents,
        status=PaymentStatus.COMPLETED,  # Replace when wiring a real PSP + webhooks
        payment_method=payment_method,
        payer_id=payer_id,
        description=desc,
        transaction_ref=f"MUEFS-{uuid4().hex}",
        processed_at=datetime.now(UTC),
    )
    db.add(payment)
    await db.flush()
    return payment
