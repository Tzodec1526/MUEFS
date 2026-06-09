"""Centralized authorization for case and document access (court / compliance).

A ``user_id`` of ``None`` means an anonymous public visitor (no account). Anonymous
and authenticated users alike may view non-sealed dockets and non-confidential documents
(public transparency); the anonymous path simply has no elevated grants, so every sealed,
confidential, or draft check fails closed for it.

Non-sealed matters: anyone (including anonymous) may view the case docket and non-confidential
documents. Draft filings remain visible only to the filer and court staff.
Sealed matters: litigants (party-linked accounts), counsel of record (attorney_* rows,
matched by linked account or a verified bar number), filer-on-case, court staff, and
system admin — never anonymous.
"""

from __future__ import annotations

from sqlalchemy import and_, false, or_, select
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
    db: AsyncSession, user_id: int | None, court_id: int
) -> bool:
    if user_id is None:
        return False
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


async def user_may_read_sealed_case(db: AsyncSession, user_id: int | None, case_id: int) -> bool:
    """Sealed docket: litigants, counsel of record, filer-on-case, court staff, admin."""
    if user_id is None:
        return False  # anonymous public visitors never reach sealed matters
    case_row = await db.execute(select(Case).where(Case.id == case_id))
    case = case_row.scalar_one_or_none()
    if not case or not case.is_sealed:
        return False

    user_row = await db.execute(select(User).where(User.id == user_id))
    user = user_row.scalar_one_or_none()
    if not user or not user.is_active:
        return False

    if user.user_type == UserType.ADMIN:
        return True

    if await user_is_court_staff_for_court(db, user_id, case.court_id):
        return True

    # Litigant: user_id on a row that is not attorney-of-record (plaintiff, defendant, …).
    litigant_q = await db.execute(
        select(CaseParticipant.id).where(
            CaseParticipant.case_id == case_id,
            CaseParticipant.user_id == user_id,
            CaseParticipant.role.notin_(_ATTORNEY_OF_RECORD_ROLES),
        )
    )
    if litigant_q.scalar_one_or_none() is not None:
        return True

    # Counsel of record only: attorney_* rows, matched by linked account or a *verified*
    # bar number on that row. A self-asserted (unverified) bar number never grants sealed
    # access — public self-registration leaves bar_number_verified False, so it cannot be
    # used to impersonate counsel of record.
    bar_match = (
        and_(
            CaseParticipant.attorney_bar_number.is_not(None),
            CaseParticipant.attorney_bar_number == user.bar_number,
        )
        if user.bar_number is not None and user.bar_number_verified
        else false()
    )
    counsel_cond = [
        CaseParticipant.case_id == case_id,
        CaseParticipant.role.in_(_ATTORNEY_OF_RECORD_ROLES),
        or_(
            CaseParticipant.user_id == user_id,
            bar_match,
        ),
    ]
    counsel_q = await db.execute(select(CaseParticipant.id).where(*counsel_cond))
    if counsel_q.scalar_one_or_none() is not None:
        return True

    fil_q = await db.execute(
        select(FilingEnvelope.id).where(
            FilingEnvelope.case_id == case_id,
            FilingEnvelope.filer_id == user_id,
        )
    )
    if fil_q.scalar_one_or_none() is not None:
        return True

    return False


async def user_may_read_case(db: AsyncSession, user_id: int | None, case_id: int) -> bool:
    """Non-sealed: anyone, including anonymous public visitors. Sealed: restricted list."""
    case_row = await db.execute(select(Case).where(Case.id == case_id))
    case = case_row.scalar_one_or_none()
    if not case:
        return False

    # A signed-in account must still be active; anonymous (user_id None) skips this.
    if user_id is not None:
        user_row = await db.execute(select(User).where(User.id == user_id))
        user = user_row.scalar_one_or_none()
        if not user or not user.is_active:
            return False

    if not case.is_sealed:
        return True

    return await user_may_read_sealed_case(db, user_id, case_id)


async def user_may_read_filing_envelope(
    db: AsyncSession, user_id: int | None, envelope: FilingEnvelope
) -> bool:
    if envelope.filer_id == user_id:
        return True
    if await user_is_court_staff_for_court(db, user_id, envelope.court_id):
        return True

    if envelope.case_id is None:
        return False

    case_row = await db.execute(select(Case).where(Case.id == envelope.case_id))
    case = case_row.scalar_one_or_none()
    if not case:
        return False

    if case.is_sealed:
        return await user_may_read_sealed_case(db, user_id, envelope.case_id)

    if envelope.status == FilingStatus.DRAFT:
        return False

    return envelope.status in _PUBLIC_DOCKET_FILING_STATUSES


async def user_may_read_document(
    db: AsyncSession, user_id: int | None, doc: FilingDocument
) -> bool:
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
