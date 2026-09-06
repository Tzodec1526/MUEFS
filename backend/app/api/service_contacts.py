"""Court-reviewed service instructions. These records do not transmit documents."""

from datetime import UTC, datetime
from typing import Annotated, Self

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.audit import AuditLog
from app.models.case import Case, CaseParticipant
from app.models.notification import ServiceContact, ServiceMethod
from app.models.user import User
from app.services import audit_service
from app.services.case_participant_service import participant_snapshot, require_case_staff
from app.services.service_contact_service import contact_snapshot, routing_issues
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(tags=["Service instructions"])
RecordId = Annotated[int, Path(ge=1, le=2_147_483_647)]


class ContactChange(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    method: ServiceMethod
    email: EmailStr | None = Field(None, max_length=255)
    address: str | None = Field(None, min_length=1, max_length=2000)
    is_active: bool = True
    authority: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=0)
    expected_participant_version: int = Field(ge=0)

    @model_validator(mode="after")
    def destination_matches_method(self) -> Self:
        if self.method == ServiceMethod.ELECTRONIC:
            if not self.email or self.address:
                raise ValueError("Electronic instructions require an email and no postal address")
        elif not self.address or self.email:
            raise ValueError("Mail or hand-delivery instructions require an address and no email")
        return self


@router.get("/cases/{case_id}/participants/{participant_id}/service-contact")
async def service_instructions(
    case_id: RecordId,
    participant_id: RecordId,
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(get_current_user),
):
    case = await require_case_staff(db, actor, case_id)
    participant = await db.get(CaseParticipant, participant_id)
    if not participant or participant.case_id != case.id:
        raise HTTPException(404, "Participant not found on this case")
    account = await db.get(User, participant.user_id) if participant.user_id else None
    contact = await db.scalar(
        select(ServiceContact).where(
            ServiceContact.participant_id == participant.id,
            ServiceContact.case_id == case.id,
        )
    )
    return {
        "court_id": case.court_id,
        "case_number": case.case_number,
        "title": case.title,
        "participant_version": case.participant_version,
        "participant": participant_snapshot(participant),
        "verified_email": account.verified_email if account else None,
        "can_edit": participant.user_id != actor.id
        and (not contact or contact.user_id != actor.id),
        "contact": contact_snapshot(contact) if contact else None,
        "issues": routing_issues(case, participant, account, contact) if contact else [],
    }


@router.put("/cases/{case_id}/participants/{participant_id}/service-contact")
async def save_service_instructions(
    case_id: RecordId,
    participant_id: RecordId,
    data: ContactChange,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(get_current_user),
):
    # Match participant management's actor-before-case lock order. The case lock also
    # serializes creation of a participant's first contact and participant reassignments.
    actor = await db.scalar(
        select(User)
        .where(User.id == current_user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    case = await db.scalar(
        select(Case)
        .where(Case.id == case_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if actor is None:
        raise HTTPException(403, "Account is unavailable")
    case = await require_case_staff(db, actor, case_id)
    if case.participant_version != data.expected_participant_version:
        raise HTTPException(409, "The participant records changed. Refresh before saving")
    participant = await db.scalar(
        select(CaseParticipant)
        .where(
            CaseParticipant.id == participant_id,
            CaseParticipant.case_id == case_id,
        )
        .execution_options(populate_existing=True)
    )
    if not participant:
        raise HTTPException(404, "Participant not found on this case")
    contact = await db.scalar(
        select(ServiceContact)
        .where(
            ServiceContact.participant_id == participant.id,
        )
        .execution_options(populate_existing=True)
    )
    if participant.user_id == actor.id or (contact and contact.user_id == actor.id):
        raise HTTPException(409, "Another court staff member must manage your service instructions")
    if contact and contact.case_id != case.id:
        raise HTTPException(
            409, "The legacy contact belongs to another case and needs reconciliation"
        )
    if (contact.version if contact else 0) != data.expected_version:
        raise HTTPException(409, "The service instructions changed. Refresh before saving")
    before = contact_snapshot(contact) if contact else None
    values = {
        "participant_snapshot": participant_snapshot(participant),
        "user_id": participant.user_id,
        "name": participant.party_name,
        "method": data.method,
        "email": str(data.email).lower() if data.email else None,
        "address": data.address,
        "is_active": data.is_active,
        "authority": data.authority,
    }
    # Validate a proposal before touching the persisted contact or its retained history.
    proposal = ServiceContact(case_id=case.id, participant_id=participant.id, **values)
    account = await db.get(User, participant.user_id) if participant.user_id else None
    if data.is_active:
        issues = routing_issues(case, participant, account, proposal)
        if issues:
            raise HTTPException(422, " ".join(issues))
    if contact and all(getattr(contact, key) == value for key, value in values.items()):
        return {"id": contact.id, "version": contact.version}
    if contact is None:
        contact = proposal
        db.add(contact)
    else:
        for key, value in values.items():
            setattr(contact, key, value)
    contact.version = data.expected_version + 1
    contact.reviewed_at = datetime.now(UTC)
    contact.reviewer_id = actor.id
    await db.flush()
    await audit_service.log_action(
        db,
        user_id=actor.id,
        action="case.service_contact_changed",
        entity_type="case",
        entity_id=case.id,
        details={
            "participant_id": participant.id,
            "actor_name": actor.full_name,
            "reason": data.reason,
            "before": before,
            "after": contact_snapshot(contact),
        },
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )
    return {"id": contact.id, "version": contact.version}


@router.get("/cases/{case_id}/participants/{participant_id}/service-contact/history")
async def service_instruction_history(
    case_id: RecordId,
    participant_id: RecordId,
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(get_current_user),
):
    await require_case_staff(db, actor, case_id)
    filters = (
        AuditLog.entity_type == "case",
        AuditLog.entity_id == case_id,
        AuditLog.action == "case.service_contact_changed",
        AuditLog.details["participant_id"].as_integer() == participant_id,
    )
    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*filters)) or 0
    rows = await db.scalars(
        select(AuditLog)
        .where(*filters)
        .order_by(AuditLog.id.desc())
        .offset((page - 1) * 25)
        .limit(25)
    )
    return {
        "total": total,
        "events": [
            {
                "id": row.id,
                "details": row.details,
                "occurred_at": row.timestamp.replace(
                    tzinfo=row.timestamp.tzinfo or UTC
                ).isoformat(),
            }
            for row in rows
        ],
    }
