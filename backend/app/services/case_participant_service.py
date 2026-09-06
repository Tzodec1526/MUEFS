"""Court-reviewed participant records; appearance data is not inferred from acceptance."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.case import COUNSEL_ROLES, Case, CaseParticipant
from app.models.user import User, UserType
from app.schemas.case_participants import ParticipantChange
from app.services import access_service, audit_service

PARTICIPANT_FIELDS = (
    "id",
    "party_name",
    "role",
    "user_id",
    "attorney_bar_number",
    "represented_party_name",
    "is_active",
    "access_enabled",
)


def participant_snapshot(participant: CaseParticipant) -> dict:
    return {field: getattr(participant, field) for field in PARTICIPANT_FIELDS}


async def require_case_staff(db: AsyncSession, actor: User, case_id: int) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    if not actor.is_active or not await access_service.user_is_court_staff_for_court(
        db,
        actor.id,
        case.court_id,
    ):
        raise HTTPException(403, "A staff assignment for this court is required")
    return case


async def change_participant(
    db: AsyncSession,
    actor_id: int,
    case_id: int,
    participant_id: int | None,
    data: ParticipantChange,
    *,
    context: dict,
) -> CaseParticipant:
    # Lock the actor before the case, and refresh permission state after a concurrent
    # account/court revocation. Case versioning prevents one editor overwriting another.
    actor = await db.scalar(
        select(User)
        .where(User.id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if actor is None:
        raise HTTPException(403, "Account is unavailable")
    case = await db.scalar(
        select(Case)
        .where(Case.id == case_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    case = await require_case_staff(db, actor, case_id)
    if case.participant_version != data.expected_version:
        raise HTTPException(409, "The case access records changed. Refresh before saving")
    participant = await db.get(CaseParticipant, participant_id) if participant_id else None
    if participant_id and (participant is None or participant.case_id != case.id):
        raise HTTPException(404, "Participant not found on this case")
    account = None
    if data.account_email:
        matches = list(
            await db.scalars(
                select(User).where(func.lower(User.email) == data.account_email.lower()).limit(2)
            )
        )
        if not matches:
            raise HTTPException(422, "This email has no provisioned account")
        if len(matches) > 1:
            raise HTTPException(
                422, "This email matches multiple accounts. Resolve their identities first"
            )
        account = matches[0]
        if data.access_enabled and (
            not account.is_active or (not account.keycloak_id and not settings.allow_demo_mode)
        ):
            raise HTTPException(
                422, "Access requires an active account bound to the identity provider"
            )
    if (account and account.id == actor.id) or (participant and participant.user_id == actor.id):
        raise HTTPException(409, "Another court staff member must manage your participant record")
    if (
        data.access_enabled
        and data.role in COUNSEL_ROLES
        and (
            account is None
            or account.user_type != UserType.ATTORNEY
            or not account.bar_number_verified
            or not data.attorney_bar_number
            or data.attorney_bar_number != account.bar_number
        )
    ):
        raise HTTPException(
            422, "Counsel access requires the linked attorney's matching verified bar number"
        )
    before = participant_snapshot(participant) if participant else None
    values = data.model_dump(exclude={"account_email", "reason", "expected_version"})
    values["user_id"] = account.id if account else None
    if (
        participant
        and participant.reviewed_at
        and all(getattr(participant, field) == value for field, value in values.items())
    ):
        return participant
    version = await db.scalar(
        update(Case)
        .where(
            Case.id == case_id,
            Case.participant_version == data.expected_version,
        )
        .values(participant_version=data.expected_version + 1)
        .returning(Case.participant_version)
    )
    if version is None:
        raise HTTPException(409, "The case access records changed. Refresh before saving")
    if participant is None:
        participant = CaseParticipant(case_id=case_id, **values)
        db.add(participant)
    else:
        for field, value in values.items():
            setattr(participant, field, value)
    participant.reviewed_at = datetime.now(UTC)
    await db.flush()
    await audit_service.log_action(
        db,
        user_id=actor.id,
        action="case.participant_created" if before is None else "case.participant_changed",
        entity_type="case",
        entity_id=case_id,
        details={
            "participant_id": participant.id,
            "actor_name": actor.full_name,
            "reason": data.reason,
            "before": before,
            "after": participant_snapshot(participant),
        },
        **context,
    )
    return participant
