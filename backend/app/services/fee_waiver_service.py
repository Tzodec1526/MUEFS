"""Court-scoped waiver authority, independent from review of the filing itself."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.user import CourtRole, UserCourtRole
from app.schemas.filing import FeeWaiverState


async def waiver_state(db: AsyncSession, filing: FilingEnvelope, user_id: int) -> FeeWaiverState:
    actions: list[str] = []
    if (
        filing.fee_waiver_requested
        and filing.fee_waiver_granted is None
        and filing.submitted_at is not None
        and filing.filer_id != user_id
        and filing.status not in (FilingStatus.REJECTED, FilingStatus.SERVED)
    ):
        roles = set(
            await db.scalars(
                select(UserCourtRole.role).where(
                    UserCourtRole.user_id == user_id,
                    UserCourtRole.court_id == filing.court_id,
                )
            )
        )
        if CourtRole.JUDGE in roles:
            actions.extend(["grant_judicial", "deny_judicial"])
        if CourtRole.CLERK in roles and filing.fee_waiver_referred_at is None:
            actions.extend(["grant_public_assistance", "grant_legal_services", "refer"])
    return FeeWaiverState(
        granted=filing.fee_waiver_granted,
        referred_at=filing.fee_waiver_referred_at,
        decided_at=filing.fee_waiver_decided_at,
        amount_due_cents=filing.fee_waiver_amount_due_cents,
        payment_id=filing.payment_id,
        can_pay=(
            filing.filer_id == user_id
            and filing.fee_waiver_granted is False
            and filing.payment_id is None
            and (filing.fee_waiver_amount_due_cents or 0) > 0
            and filing.status not in (FilingStatus.REJECTED, FilingStatus.SERVED)
        ),
        allowed_actions=actions,
        payments_simulated=settings.payments_are_simulated,
    )
