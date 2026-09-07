"""Centralized authorization for case and document access (court / compliance).

A ``user_id`` of ``None`` means an anonymous public visitor (no account). Anonymous
and authenticated users alike may view non-sealed dockets and non-confidential documents
(public transparency); the anonymous path simply has no elevated grants, so every sealed,
confidential, or draft check fails closed for it.

Non-sealed matters: anyone (including anonymous) may view the case docket and non-confidential
documents. Only accepted filings appear on the public docket. Draft, pending, rejected,
returned, and service-only envelopes remain visible only to the filer and court staff.
Sealed matters: accounts explicitly granted access through active participant records,
court staff, and system admin — never anonymous. Counsel grants also require a matching
verified bar number. Filing acceptance alone does not grant access to the rest of a case.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, false, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import COUNSEL_ROLES, Case, CaseParticipant
from app.models.filing import PRIVATE_DOCUMENT_TYPES, FilingDocument, FilingEnvelope, FilingStatus
from app.models.user import CourtRole, User, UserCourtRole, UserType

# Filings that may appear on a public (non-sealed) docket to non-parties.
# Pending, rejected, returned, and service-only envelopes stay off the public record.
PUBLIC_DOCKET_FILING_STATUSES = frozenset({
    FilingStatus.ACCEPTED,
})

async def user_has_court_administrator_assignment(
    db: AsyncSession, user_id: int, court_id: int,
) -> bool:
    return bool(await db.scalar(select(select(UserCourtRole.id).where(
        UserCourtRole.user_id == user_id, UserCourtRole.court_id == court_id,
        UserCourtRole.role == CourtRole.ADMIN,
    ).exists())))


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
    counsel_eligible = (
        CaseParticipant.attorney_bar_number == user.bar_number
        if user.user_type == UserType.ATTORNEY and user.bar_number and user.bar_number_verified
        else false()
    )
    participant_grant = select(CaseParticipant.id).where(
        CaseParticipant.case_id == Case.id,
        CaseParticipant.user_id == user.id,
        CaseParticipant.is_active.is_(True),
        CaseParticipant.access_enabled.is_(True),
        or_(
            CaseParticipant.role.not_in(COUNSEL_ROLES), counsel_eligible,
        ),
    ).correlate(Case).exists()
    staff_grant = select(UserCourtRole.id).where(
        UserCourtRole.court_id == Case.court_id,
        UserCourtRole.user_id == user.id,
        UserCourtRole.role.in_([CourtRole.CLERK, CourtRole.JUDGE, CourtRole.ADMIN]),
    ).correlate(Case).exists()
    return or_(public, participant_grant, staff_grant)


async def user_may_read_sealed_case(db: AsyncSession, user_id: int | None, case_id: int) -> bool:
    """Sealed docket: explicit participant grants, court staff and system administrators."""
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


async def user_may_file_on_case(db: AsyncSession, user_id: int, case_id: int) -> bool:
    """Subsequent filings require a court-reviewed participant grant, not public docket read."""
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        return False
    counsel = (
        CaseParticipant.attorney_bar_number == user.bar_number
        if user.user_type == UserType.ATTORNEY and user.bar_number and user.bar_number_verified
        else false()
    )
    participation = await db.scalar(
        select(CaseParticipant.id)
        .where(
            CaseParticipant.case_id == case_id,
            CaseParticipant.user_id == user.id,
            CaseParticipant.is_active.is_(True),
            CaseParticipant.access_enabled.is_(True),
            CaseParticipant.reviewed_at.is_not(None),
            or_(CaseParticipant.role.not_in(COUNSEL_ROLES), counsel),
        )
        .limit(1)
    )
    if not participation:
        return False
    return await user_may_read_case(db, user_id, case_id)


async def user_may_read_filing_envelope(
    db: AsyncSession, user_id: int | None, envelope: FilingEnvelope
) -> bool:
    if envelope.filer_id == user_id:
        return True
    if await user_is_court_staff_for_court(db, user_id, envelope.court_id):
        return True

    if envelope.status not in PUBLIC_DOCKET_FILING_STATUSES:
        return False

    if envelope.case_id is None:
        return False

    case_row = await db.execute(select(Case).where(Case.id == envelope.case_id))
    case = case_row.scalar_one_or_none()
    if not case:
        return False

    if case.is_sealed:
        return await user_may_read_sealed_case(db, user_id, envelope.case_id)

    return True


async def user_may_read_document(
    db: AsyncSession, user_id: int | None, doc: FilingDocument
) -> bool:
    env_row = await db.execute(
        select(FilingEnvelope).where(FilingEnvelope.id == doc.envelope_id)
    )
    envelope = env_row.scalar_one_or_none()
    if not envelope:
        return False

    # Superseded documents remain available to their filer and court staff, even
    # after a corrected filing is accepted. They must never enter the public docket.
    if (doc.is_confidential or doc.document_type_code in PRIVATE_DOCUMENT_TYPES
            or doc.removed_at is not None):
        if envelope.filer_id == user_id:
            return True
        return await user_is_court_staff_for_court(db, user_id, envelope.court_id)

    return await user_may_read_filing_envelope(db, user_id, envelope)
