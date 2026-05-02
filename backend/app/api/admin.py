from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.audit import AuditLog
from app.models.case import Case
from app.models.court import CaseType, Court, CourtType
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.user import User, UserType

_ALL_COURT_TYPES: tuple[CourtType, ...] = tuple(CourtType)

router = APIRouter(prefix="/admin", tags=["Admin"])


async def _require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.user_type != UserType.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


@router.get("/stats")
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(_require_admin),
):
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
    _admin: User = Depends(_require_admin),
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
                "user_agent": e.user_agent,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            }
            for e in entries
        ],
        "page": page,
        "page_size": page_size,
    }


@router.get("/public-stats")
async def get_public_stats(
    db: AsyncSession = Depends(get_db),
):
    """Public statistics — no auth required. For the coverage dashboard.

    Uses a single GROUP BY to count courts per type instead of one query per enum value,
    and groups filing-status counts in one round trip. ~6 queries → 3.
    """
    by_type_rows = (await db.execute(
        select(Court.court_type, func.count(Court.id)).group_by(Court.court_type)
    )).all()
    court_type_counts: dict[str, int] = {ct.value: 0 for ct in _ALL_COURT_TYPES}
    for ct_value, count in by_type_rows:
        # ct_value may be enum or raw string depending on dialect
        key = ct_value.value if hasattr(ct_value, "value") else str(ct_value)
        court_type_counts[key] = int(count)

    county_count = (await db.execute(
        select(func.count(distinct(Court.county))).select_from(Court)
    )).scalar() or 0

    case_type_count = (await db.execute(
        select(func.count()).select_from(CaseType)
    )).scalar() or 0

    filing_status_rows = (await db.execute(
        select(FilingEnvelope.status, func.count(FilingEnvelope.id))
        .group_by(FilingEnvelope.status)
    )).all()
    total_filings = 0
    accepted_filings = 0
    for status_value, count in filing_status_rows:
        n = int(count)
        total_filings += n
        if status_value == FilingStatus.ACCEPTED:
            accepted_filings = n

    return {
        "courts_by_type": court_type_counts,
        "total_courts": sum(court_type_counts.values()),
        "counties_covered": county_count,
        "total_case_types": case_type_count,
        "total_filings": total_filings,
        "accepted_filings": accepted_filings,
    }
