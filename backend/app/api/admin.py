from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit import AuditLog
from app.models.case import Case
from app.models.court import Court
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats")
async def get_system_stats(db: AsyncSession = Depends(get_db)):
    total_courts = (await db.execute(select(func.count()).select_from(Court))).scalar() or 0
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    total_cases = (await db.execute(select(func.count()).select_from(Case))).scalar() or 0
    total_filings = (
        await db.execute(select(func.count()).select_from(FilingEnvelope))
    ).scalar() or 0
    pending_filings = (
        await db.execute(
            select(func.count())
            .select_from(FilingEnvelope)
            .where(
                FilingEnvelope.status.in_(
                    [FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW]
                )
            )
        )
    ).scalar() or 0

    return {
        "total_courts": total_courts,
        "total_users": total_users,
        "total_cases": total_cases,
        "total_filings": total_filings,
        "pending_review": pending_filings,
    }


@router.get("/audit-log")
async def get_audit_log(
    action: str | None = None,
    entity_type: str | None = None,
    user_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(AuditLog).order_by(AuditLog.timestamp.desc())

    if action:
        query = query.where(AuditLog.action == action)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    entries = result.scalars().all()

    return {
        "entries": [
            {
                "id": e.id,
                "user_id": e.user_id,
                "action": e.action,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "details": e.details,
                "ip_address": e.ip_address,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            }
            for e in entries
        ],
        "page": page,
        "page_size": page_size,
    }
