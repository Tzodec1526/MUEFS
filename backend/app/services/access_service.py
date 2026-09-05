"""Centralized authorization for case and document access (court / compliance).

A ``user_id`` of ``None`` means an anonymous public visitor (no account). Anonymous
and authenticated users alike may view non-sealed dockets and non-confidential documents
(public transparency); the anonymous path simply has no elevated grants, so every sealed,
confidential, or draft check fails closed for it.

Non-sealed matters: anyone (including anonymous) may view the case docket and non-confidential
documents. Only accepted filings appear on the public docket. Draft, pending, rejected,
returned, and service-only envelopes remain visible only to the filer and court staff.
Sealed matters: litigants (party-linked accounts), counsel of record (attorney_* rows,
matched by linked account or a verified bar number), filer-on-case (accepted envelopes
only), court staff, and system admin — never anonymous.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, and_, false, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseParticipant, ParticipantRole
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.user import CourtRole, User, UserCourtRole, UserType

# Filings that may appear on a public (non-sealed) docket to non-parties.
# Pending, rejected, returned, and service-only envelopes stay off the public record.
PUBLIC_DOCKET_FILING_STATUSES = frozenset({
    FilingStatus.ACCEPTED,
})

# Standing as "filer on this case" requires an accepted envelope, not a draft.
_FILER_ON_CASE_STATUSES = frozenset({
    FilingStatus.ACCEPTED,
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
    staff_role = select(UserCourtRole.id).where(
        UserCourtRole.user_id == user_id,
        UserCourtRole.court_id == court_id,
        UserCourtRole.role.in_([CourtRole.CLERK, CourtRole.JUDGE, CourtRole.ADMIN]),
    ).exists()
    return bool(await db.scalar(select(staff_role)))


def case_visibility_filter(user: User | None) -> ColumnElement[bool]:
    """Shared SQL predicate for both single-case reads and saved-case listings."""
    public = Case.is_sealed.is_(False)
    if user is None:
        return public
    if not user.is_active:
        return false()
    if user.user_type == UserType.ADMIN:
        return true()
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
    participant_grant = select(CaseParticipant.id).where(
        CaseParticipant.case_id == Case.id,
        or_(
            CaseParticipant.user_id == user.id,
            and_(CaseParticipant.role.in_(_ATTORNEY_OF_RECORD_ROLES), bar_match),
        ),
    ).correlate(Case).exists()
    filer_grant = (
        select(FilingEnvelope.id).where(
            FilingEnvelope.case_id == Case.id,
            FilingEnvelope.filer_id == user.id,
            FilingEnvelope.status.in_(_FILER_ON_CASE_STATUSES),
        ).correlate(Case).exists()
    )
    staff_grant = select(UserCourtRole.id).where(
        UserCourtRole.court_id == Case.court_id,
        UserCourtRole.user_id == user.id,
        UserCourtRole.role.in_([CourtRole.CLERK, CourtRole.JUDGE, CourtRole.ADMIN]),
    ).correlate(Case).exists()
    return or_(public, participant_grant, filer_grant, staff_grant)


async def user_may_read_sealed_case(db: AsyncSession, user_id: int | None, case_id: int) -> bool:
    """Sealed docket: litigants, counsel of record, filer-on-case, court staff, admin."""
    if user_id is None:
        return False
    user = await db.get(User, user_id)
    return bool(user and await db.scalar(select(Case.id).where(
        Case.id == case_id, Case.is_sealed.is_(True), case_visibility_filter(user),
    )))


async def user_may_read_case(db: AsyncSession, user_id: int | None, case_id: int) -> bool:
    """Non-sealed: anyone, including anonymous public visitors. Sealed: restricted list."""
    user = await db.get(User, user_id) if user_id is not None else None
    if user_id is not None and user is None:
        return False
    return bool(await db.scalar(select(Case.id).where(
        Case.id == case_id, case_visibility_filter(user),
    )))


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

    return envelope.status in PUBLIC_DOCKET_FILING_STATUSES


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
