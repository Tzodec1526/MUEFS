"""Court staff manage portal participant records and explicit restricted-case access."""


from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, lock_current_user
from app.api.params import Page, RecordId
from app.database import get_db
from app.models.audit import AuditLog
from app.models.case import Case, CaseParticipant
from app.models.user import User
from app.schemas.case_participants import ParticipantChange, PublicCaseAccessChange
from app.schemas.common import MAX_RECORD_ID
from app.services import access_service, audit_service
from app.services import case_participant_service as participants
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(tags=["Case participants"])


@router.get("/clerk/cases")
async def court_cases(
    court_id: int = Query(ge=1, le=MAX_RECORD_ID),
    case_number: str | None = Query(default=None, max_length=50),
    before_id: int | None = Query(default=None, ge=1, le=MAX_RECORD_ID),
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(get_current_user),
):
    if not await access_service.user_is_court_staff_for_court(db, actor.id, court_id):
        raise HTTPException(403, "A staff assignment for this court is required")
    query = select(Case).where(Case.court_id == court_id)
    if case_number and case_number.strip():
        query = query.where(Case.case_number == case_number.strip())
    if before_id is not None:
        query = query.where(Case.id < before_id)
    rows = list(await db.scalars(query.order_by(Case.id.desc()).limit(26)))
    return {
        "cases": [
            {
                "id": row.id,
                "case_number": row.case_number,
                "title": row.title,
                "is_sealed": row.is_sealed,
                "status": row.status,
            }
            for row in rows[:25]
        ],
        "next_before_id": rows[24].id if len(rows) > 25 else None,
    }


@router.get("/cases/{case_id}/participants")
async def participant_records(
    case_id: RecordId,
    page: Page = 1,
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(get_current_user),
):
    case = await participants.require_case_staff(db, actor, case_id)
    total = await db.scalar(
        select(func.count())
        .select_from(CaseParticipant)
        .where(
            CaseParticipant.case_id == case_id,
        )
    )
    records = await db.execute(
        select(CaseParticipant, User.email)
        .outerjoin(User, User.id == CaseParticipant.user_id)
        .where(
            CaseParticipant.case_id == case_id,
        )
        .order_by(CaseParticipant.id)
        .offset((page - 1) * 25)
        .limit(25),
    )
    return {
        "case_id": case.id,
        "case_number": case.case_number,
        "title": case.title,
        "is_sealed": case.is_sealed,
        "participant_version": case.participant_version,
        "participants": [
            {
                **participants.participant_snapshot(record),
                "account_email": email,
                "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
            }
            for record, email in records
        ],
        "page": page,
        "total": total or 0,
        "actor_id": actor.id,
    }


@router.post("/cases/{case_id}/participants", status_code=201)
async def add_participant(
    case_id: RecordId,
    data: ParticipantChange,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(get_current_user),
):
    async with db.begin_nested():
        record = await participants.change_participant(
            db,
            actor.id,
            case_id,
            None,
            data,
            context={"ip_address": client_ip(request), "user_agent": client_user_agent(request)},
        )
    return {"id": record.id}


@router.put("/cases/{case_id}/participants/{participant_id}")
async def update_participant(
    case_id: RecordId,
    participant_id: RecordId,
    data: ParticipantChange,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(get_current_user),
):
    async with db.begin_nested():
        record = await participants.change_participant(
            db,
            actor.id,
            case_id,
            participant_id,
            data,
            context={"ip_address": client_ip(request), "user_agent": client_user_agent(request)},
        )
    return {"id": record.id}


@router.put("/cases/{case_id}/public-access")
async def change_public_access(
    case_id: RecordId,
    data: PublicCaseAccessChange,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(get_current_user),
):
    actor = await lock_current_user(db, actor.id)
    await participants.require_case_staff(db, actor, case_id)
    if await db.scalar(select(CaseParticipant.id).where(
        CaseParticipant.case_id == case_id, CaseParticipant.user_id == actor.id,
        CaseParticipant.is_active.is_(True),
    ).limit(1)):
        raise HTTPException(403, "Another court reviewer must change access to your own case")
    case = await db.scalar(select(Case).where(Case.id == case_id).with_for_update()
                           .execution_options(populate_existing=True))
    if case is None:
        raise HTTPException(404, "Case not found")
    if case.participant_version != data.expected_version:
        raise HTTPException(409, "Case access changed. Refresh and review before saving")
    if case.is_sealed == data.is_sealed:
        return {"is_sealed": case.is_sealed, "participant_version": case.participant_version}
    if not data.is_sealed and not data.confirm_public_release:
        raise HTTPException(422, "Confirm the court's instruction to restore public case access")
    before = {"is_sealed": case.is_sealed, "participant_version": case.participant_version}
    # Participant grants and public access share a revision: either invalidates older editors.
    version = await db.scalar(update(Case).where(
        Case.id == case_id, Case.participant_version == data.expected_version,
    ).values(is_sealed=data.is_sealed, participant_version=data.expected_version + 1)
        .returning(Case.participant_version))
    if version is None:
        raise HTTPException(409, "Case access changed. Refresh and review before saving")
    after = {"is_sealed": data.is_sealed, "participant_version": version}
    await audit_service.log_action(
        db, user_id=actor.id, action="case.public_access_changed", entity_type="case",
        entity_id=case_id,
        details={"actor_name": actor.full_name, "case_number": case.case_number,
                 "reason": data.reason, "authority_reference": data.authority_reference,
                 "confirmed_public_release": data.confirm_public_release,
                 "before": before, "after": after},
        ip_address=client_ip(request), user_agent=client_user_agent(request),
    )
    return after


@router.get("/cases/{case_id}/participants/history")
async def participant_history(
    case_id: RecordId,
    page: Page = 1,
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(get_current_user),
):
    await participants.require_case_staff(db, actor, case_id)
    query = select(AuditLog).where(
        AuditLog.entity_type == "case",
        AuditLog.entity_id == case_id,
        or_(AuditLog.action.startswith("case.participant"),
            AuditLog.action == "case.public_access_changed"),
    )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = await db.scalars(query.order_by(AuditLog.id.desc()).offset((page - 1) * 25).limit(25))
    return {
        "total": total or 0,
        "events": [
            {
                "id": row.id,
                "action": row.action,
                "details": row.details,
                "occurred_at": row.timestamp.isoformat(),
            }
            for row in rows
        ],
    }
