"""Court-scoped waiver authority, independent from review of the filing itself."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filing import FilingEnvelope, FilingStatus
from app.models.user import CourtRole, UserCourtRole
from app.schemas.filing import FeeWaiverState
from app.services.fee_assessment_service import fee_state


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
    fees = await fee_state(db, filing, user_id)
    return FeeWaiverState(
        granted=filing.fee_waiver_granted,
        referred_at=filing.fee_waiver_referred_at,
        decided_at=filing.fee_waiver_decided_at,
        amount_due_cents=filing.fee_waiver_amount_due_cents,
        balance_due_cents=fees.balance_due_cents,
        fee_version=fees.version,
        can_pay=filing.fee_waiver_granted is False and fees.can_pay,
        allowed_actions=actions,
        payments_simulated=fees.payments_simulated,
    )
