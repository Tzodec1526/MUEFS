"""Court staff manage portal participant records and explicit restricted-case access."""

from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.audit import AuditLog
from app.models.case import Case, CaseParticipant
from app.models.user import User
from app.schemas.case_participants import ParticipantChange
from app.services import access_service
from app.services import case_participant_service as participants
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(tags=["Case participants"])


@router.get("/clerk/cases")
async def court_cases(
    court_id: int,
    case_number: str | None = Query(default=None, max_length=50),
    before_id: int | None = Query(default=None, ge=1),
    db: AsyncSession = Depends(get_db),
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
    case_id: int,
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
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
                "reviewed_at": record.reviewed_at.replace(
                    tzinfo=record.reviewed_at.tzinfo or UTC
                ).isoformat()
                if record.reviewed_at
                else None,
            }
            for record, email in records
        ],
        "page": page,
        "total": total or 0,
        "actor_id": actor.id,
    }


@router.post("/cases/{case_id}/participants", status_code=201)
async def add_participant(
    case_id: int,
    data: ParticipantChange,
    request: Request,
    db: AsyncSession = Depends(get_db),
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
    case_id: int,
    participant_id: int,
    data: ParticipantChange,
    request: Request,
    db: AsyncSession = Depends(get_db),
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


@router.get("/cases/{case_id}/participants/history")
async def participant_history(
    case_id: int,
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    await participants.require_case_staff(db, actor, case_id)
    query = select(AuditLog).where(
        AuditLog.entity_type == "case",
        AuditLog.entity_id == case_id,
        AuditLog.action.startswith("case.participant"),
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
                "occurred_at": row.timestamp.replace(
                    tzinfo=row.timestamp.tzinfo or UTC
                ).isoformat(),
            }
            for row in rows
        ],
    }
