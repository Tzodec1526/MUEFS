"""Centralized authorization for case and document access (court / compliance).

Fail closed: deny unless a concrete rule matches. Rules approximate real docket
access (party of record, counsel of record, court staff, system admin).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseParticipant
from app.models.filing import FilingDocument, FilingEnvelope
from app.models.user import CourtRole, User, UserCourtRole, UserType


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


async def user_may_read_case(db: AsyncSession, user_id: int, case_id: int) -> bool:
    case_row = await db.execute(select(Case).where(Case.id == case_id))
    case = case_row.scalar_one_or_none()
    if not case:
        return False

    user_row = await db.execute(select(User).where(User.id == user_id))
    user = user_row.scalar_one_or_none()
    if not user:
        return False

    if user.user_type == UserType.ADMIN:
        return True

    if await user_is_court_staff_for_court(db, user_id, case.court_id):
        return True

    # Party / counsel linked to portal account
    part_q = await db.execute(
        select(CaseParticipant.id).where(
            CaseParticipant.case_id == case_id,
            CaseParticipant.user_id == user_id,
        )
    )
    if part_q.scalar_one_or_none() is not None:
        return True

    # Attorney of record (bar number on participant row)
    if user.bar_number:
        bar_q = await db.execute(
            select(CaseParticipant.id).where(
                CaseParticipant.case_id == case_id,
                CaseParticipant.attorney_bar_number == user.bar_number,
            )
        )
        if bar_q.scalar_one_or_none() is not None:
            return True

    # Filer on any envelope tied to this case (pending or historical)
    fil_q = await db.execute(
        select(FilingEnvelope.id).where(
            FilingEnvelope.case_id == case_id,
            FilingEnvelope.filer_id == user_id,
        )
    )
    if fil_q.scalar_one_or_none() is not None:
        return True

    return False


async def user_may_read_filing_envelope(
    db: AsyncSession, user_id: int, envelope: FilingEnvelope
) -> bool:
    if envelope.filer_id == user_id:
        return True
    if await user_is_court_staff_for_court(db, user_id, envelope.court_id):
        return True
    if envelope.case_id is not None:
        return await user_may_read_case(db, user_id, envelope.case_id)
    return False


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
