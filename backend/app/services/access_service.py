from __future__ import annotations

from sqlalchemy import ColumnElement, false, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import COUNSEL_ROLES, Case, CaseParticipant
from app.models.filing import PRIVATE_DOCUMENT_TYPES, FilingDocument, FilingEnvelope, FilingStatus
from app.models.user import CourtRole, User, UserCourtRole, UserType

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


async def user_may_read_sealed_case(db: AsyncSession, user: User | None, case_id: int) -> bool:
    if user is None:
        return False
    return bool(await db.scalar(select(Case.id).where(
        Case.id == case_id, Case.is_sealed.is_(True), case_visibility_filter(user),
    )))


async def user_may_read_case(db: AsyncSession, user: User | None, case_id: int) -> bool:
    return bool(await db.scalar(select(Case.id).where(
        Case.id == case_id, case_visibility_filter(user),
    )))


PUBLIC_ACCOUNT_REFUSAL = "Public docket accounts cannot create or manage e-filings."


async def user_may_file_on_case(db: AsyncSession, user: User, case_id: int) -> bool:
    return (
        await user_has_filing_grant(db, user, case_id)
        and await user_may_read_case(db, user, case_id)
    )


async def user_has_filing_grant(db: AsyncSession, user: User, case_id: int) -> bool:
    if not user.is_active or user.user_type == UserType.PUBLIC:
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
    return bool(participation)


async def user_may_read_filing_envelope(
    db: AsyncSession, user: User | None, envelope: FilingEnvelope
) -> bool:
    user_id = user.id if user else None
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
        return await user_may_read_sealed_case(db, user, envelope.case_id)

    return True


async def user_may_read_document(
    db: AsyncSession, user: User | None, doc: FilingDocument
) -> bool:
    user_id = user.id if user else None
    env_row = await db.execute(
        select(FilingEnvelope).where(FilingEnvelope.id == doc.envelope_id)
    )
    envelope = env_row.scalar_one_or_none()
    if not envelope:
        return False

    if (doc.is_confidential or doc.document_type_code in PRIVATE_DOCUMENT_TYPES
            or doc.removed_at is not None):
        if envelope.filer_id == user_id:
            return True
        return await user_is_court_staff_for_court(db, user_id, envelope.court_id)

    return await user_may_read_filing_envelope(db, user, envelope)
