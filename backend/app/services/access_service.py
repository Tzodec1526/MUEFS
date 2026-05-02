"""Centralized authorization for case and document access (court / compliance).

Non-sealed matters: any authenticated user may view the case docket and non-confidential
documents (public transparency). Draft filings remain visible only to the filer and court staff.
Sealed matters: litigants (party-linked accounts), counsel of record (attorney_* rows only),
filer-on-case, court staff, and system admin.

Performance: helpers accept pre-loaded ``User`` / ``Case`` objects to avoid re-querying when
the caller already holds them. The id-only signatures remain for back compat.
"""

from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseParticipant, ParticipantRole
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.user import CourtRole, User, UserCourtRole, UserType

# Filings that may appear on a public (non-sealed) docket to non-parties.
_PUBLIC_DOCKET_FILING_STATUSES = frozenset({
    FilingStatus.SUBMITTED,
    FilingStatus.UNDER_REVIEW,
    FilingStatus.ACCEPTED,
    FilingStatus.REJECTED,
    FilingStatus.RETURNED,
    FilingStatus.SERVED,
})

# Sealed matters: bar-number match only for rows of counsel of record, not incidental bar fields.
_ATTORNEY_OF_RECORD_ROLES = frozenset({
    ParticipantRole.ATTORNEY_PLAINTIFF,
    ParticipantRole.ATTORNEY_DEFENDANT,
})


async def user_is_court_staff_for_court(
    db: AsyncSession, user_id: int, court_id: int
) -> bool:
    q = await db.execute(
        select(UserCourtRole.id).where(
            UserCourtRole.user_id == user_id,
            UserCourtRole.court_id == court_id,
            UserCourtRole.role.in_(
                [CourtRole.CLERK, CourtRole.JUDGE, CourtRole.ADMIN]
            ),
        )
    )
    return q.scalar_one_or_none() is not None


async def _load_active_user(db: AsyncSession, user_id: int) -> User | None:
    row = await db.execute(select(User).where(User.id == user_id))
    user = row.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    return user


async def _load_case(db: AsyncSession, case_id: int) -> Case | None:
    row = await db.execute(select(Case).where(Case.id == case_id))
    return row.scalar_one_or_none()


async def _user_may_read_sealed_case_resolved(
    db: AsyncSession, user: User, case: Case
) -> bool:
    """Sealed docket access using already-loaded user + case."""
    if not case.is_sealed:
        return False

    if user.user_type == UserType.ADMIN:
        return True

    if await user_is_court_staff_for_court(db, user.id, case.court_id):
        return True

    # Litigant: user_id on a row that is not attorney-of-record (plaintiff, defendant, …).
    litigant_q = await db.execute(
        select(CaseParticipant.id).where(
            CaseParticipant.case_id == case.id,
            CaseParticipant.user_id == user.id,
            CaseParticipant.role.notin_(_ATTORNEY_OF_RECORD_ROLES),
        )
    )
    if litigant_q.scalar_one_or_none() is not None:
        return True

    # Counsel of record only: attorney_* rows, matched by linked account or bar on that row.
    counsel_cond = [
        CaseParticipant.case_id == case.id,
        CaseParticipant.role.in_(_ATTORNEY_OF_RECORD_ROLES),
        or_(
            CaseParticipant.user_id == user.id,
            and_(
                user.bar_number is not None,
                CaseParticipant.attorney_bar_number == user.bar_number,
            ),
        ),
    ]
    counsel_q = await db.execute(select(CaseParticipant.id).where(*counsel_cond))
    if counsel_q.scalar_one_or_none() is not None:
        return True

    fil_q = await db.execute(
        select(FilingEnvelope.id).where(
            FilingEnvelope.case_id == case.id,
            FilingEnvelope.filer_id == user.id,
        )
    )
    return fil_q.scalar_one_or_none() is not None


async def user_may_read_sealed_case(db: AsyncSession, user_id: int, case_id: int) -> bool:
    """Sealed docket: litigants, counsel of record, filer-on-case, court staff, admin."""
    case = await _load_case(db, case_id)
    if not case or not case.is_sealed:
        return False
    user = await _load_active_user(db, user_id)
    if not user:
        return False
    return await _user_may_read_sealed_case_resolved(db, user, case)


async def user_may_read_case(db: AsyncSession, user_id: int, case_id: int) -> bool:
    """Non-sealed: any signed-in user. Sealed: restricted list."""
    case = await _load_case(db, case_id)
    if not case:
        return False
    user = await _load_active_user(db, user_id)
    if not user:
        return False
    if not case.is_sealed:
        return True
    return await _user_may_read_sealed_case_resolved(db, user, case)


async def user_may_read_filing_envelope(
    db: AsyncSession, user_id: int, envelope: FilingEnvelope
) -> bool:
    if envelope.filer_id == user_id:
        return True
    if await user_is_court_staff_for_court(db, user_id, envelope.court_id):
        return True

    if envelope.case_id is None:
        return False

    case = await _load_case(db, envelope.case_id)
    if not case:
        return False

    if case.is_sealed:
        user = await _load_active_user(db, user_id)
        if not user:
            return False
        return await _user_may_read_sealed_case_resolved(db, user, case)

    if envelope.status == FilingStatus.DRAFT:
        return False

    return envelope.status in _PUBLIC_DOCKET_FILING_STATUSES


async def user_may_read_envelope_with_case(
    db: AsyncSession,
    user: User,
    envelope: FilingEnvelope,
    case: Case | None,
    is_court_staff: bool,
) -> bool:
    """Fast path: caller has already resolved user, case, and court-staff status.

    Used by docket endpoints that authorize many envelopes for the same case+user. Avoids
    one User and one Case query per envelope (N+1 → O(1) lookups).
    """
    if envelope.filer_id == user.id:
        return True
    if is_court_staff:
        return True

    if envelope.case_id is None:
        return False
    if case is None:
        return False

    if case.is_sealed:
        return await _user_may_read_sealed_case_resolved(db, user, case)

    if envelope.status == FilingStatus.DRAFT:
        return False

    return envelope.status in _PUBLIC_DOCKET_FILING_STATUSES


async def user_may_read_document(db: AsyncSession, user_id: int, doc: FilingDocument) -> bool:
    env_row = await db.execute(
        select(FilingEnvelope).where(FilingEnvelope.id == doc.envelope_id)
    )
    envelope = env_row.scalar_one_or_none()
    if not envelope:
        return False

    if doc.is_confidential:
        if envelope.filer_id == user_id:
            return True
        return await user_is_court_staff_for_court(db, user_id, envelope.court_id)

    return await user_may_read_filing_envelope(db, user_id, envelope)
