from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id, get_optional_user_id, lock_current_user
from app.api.params import Page, RecordId
from app.database import get_db
from app.models.audit import AuditLog
from app.models.court import CaseType, Court
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.schemas.court_intake import (
    CourtIntakeChange,
    CourtIntakeHistory,
    CourtIntakeResponse,
)
from app.services import audit_service
from app.services.administration_service import require_court_administrator
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(prefix="/courts", tags=["Court Intake"])


def intake_state(court: Court, case_types: list[CaseType]) -> dict:
    return {
        "court_id": court.id, "court_name": court.name, "version": court.intake_version,
        "is_efiling_enabled": court.is_efiling_enabled, "public_notice": court.intake_notice,
        "case_types": [{"id": item.id, "code": item.code, "name": item.name,
                        "is_active": item.is_active} for item in case_types],
    }


@router.get("/{court_id}/intake", response_model=CourtIntakeResponse)
async def get_intake(
    court_id: RecordId,
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int | None = Depends(get_optional_user_id),
):
    rows = (await db.execute(select(Court, CaseType)
        .outerjoin(CaseType, CaseType.court_id == Court.id).where(Court.id == court_id)
        .order_by(CaseType.name, CaseType.id).execution_options(populate_existing=True))).all()
    if not rows:
        raise HTTPException(404, "Court not found")
    court = rows[0].Court
    case_types = [row.CaseType for row in rows if row.CaseType is not None]
    user = await db.get(User, user_id) if user_id else None
    can_manage = bool(user and user.is_active and (
        user.user_type == UserType.ADMIN or await db.scalar(select(UserCourtRole.id).where(
            UserCourtRole.user_id == user_id, UserCourtRole.court_id == court_id,
            UserCourtRole.role == CourtRole.ADMIN,
        ).limit(1))
    ))
    return {**intake_state(court, case_types), "can_manage": can_manage}


@router.put("/{court_id}/intake", response_model=CourtIntakeResponse)
async def publish_intake(
    request: Request,
    court_id: RecordId,
    data: CourtIntakeChange,
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    actor = await lock_current_user(db, user_id)
    await require_court_administrator(db, actor, court_id)
    court = await db.scalar(select(Court).where(Court.id == court_id).with_for_update()
                            .execution_options(populate_existing=True))
    if court is None:
        raise HTTPException(404, "Court not found")
    if court.intake_version != data.expected_version:
        raise HTTPException(409, "Intake changed. Reload and review settings before publishing")
    case_types = list(await db.scalars(select(CaseType).where(CaseType.court_id == court_id)
                                      .order_by(CaseType.name, CaseType.id).with_for_update()
                                      .execution_options(populate_existing=True)))
    desired = {item.id: item.is_active for item in data.case_types}
    if set(desired) != {item.id for item in case_types}:
        raise HTTPException(409, "Available case types changed. Reload intake settings")
    before = intake_state(court, case_types)
    if (court.is_efiling_enabled == data.is_efiling_enabled
            and court.intake_notice == data.public_notice
            and all(item.is_active == desired[item.id] for item in case_types)):
        return {**before, "can_manage": True}
    if (not data.is_efiling_enabled or not all(desired.values())) and not data.public_notice:
        raise HTTPException(422, "Publish instructions for filers when closing electronic intake")

    court = await db.scalar(update(Court).where(
        Court.id == court_id, Court.intake_version == data.expected_version,
    ).values(
        is_efiling_enabled=data.is_efiling_enabled, intake_notice=data.public_notice,
        intake_version=data.expected_version + 1,
    ).returning(Court).execution_options(populate_existing=True))
    if court is None:
        raise HTTPException(409, "Intake changed. Reload and review settings before publishing")
    for item in case_types:
        item.is_active = desired[item.id]
    await db.flush()
    after = intake_state(court, case_types)
    await audit_service.log_action(
        db, user_id=user_id, action="court_intake_changed", entity_type="court", entity_id=court_id,
        details={"before": before, "after": after, "reason": data.reason,
                 "authority_reference": data.authority_reference,
                 "actor_name": f"{actor.first_name} {actor.last_name}"},
        ip_address=client_ip(request), user_agent=client_user_agent(request),
    )
    return {**after, "can_manage": True}


@router.get("/{court_id}/intake/history", response_model=CourtIntakeHistory)
async def intake_history(
    court_id: RecordId,
    page: Page = 1,
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    actor = await lock_current_user(db, user_id)
    await require_court_administrator(db, actor, court_id)
    filters = (AuditLog.entity_type == "court", AuditLog.entity_id == court_id,
               AuditLog.action == "court_intake_changed")
    rows = (await db.scalars(select(AuditLog).where(*filters).order_by(AuditLog.id.desc())
                             .offset((page - 1) * 25).limit(25))).all()
    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*filters)) or 0
    return {"changes": [{"id": row.id, "timestamp": row.timestamp, **(row.details or {})}
                        for row in rows], "total": total}
