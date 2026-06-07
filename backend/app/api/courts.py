from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.court import CaseType, Court, CourtType, FeeSchedule
from app.schemas.court import (
    CaseTypeResponse,
    CourtListResponse,
    CourtResponse,
    FeeScheduleResponse,
)

router = APIRouter(prefix="/courts", tags=["Courts"])


@router.get("", response_model=CourtListResponse)
async def list_courts(
    county: str | None = None,
    court_type: CourtType | None = None,
    tier: str | None = None,
    q: str | None = None,
    efiling_only: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Court)
    count_query = select(func.count()).select_from(Court)

    def _ilike(col, value: str):
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return col.ilike(f"%{escaped}%")

    if county:
        query = query.where(_ilike(Court.county, county))
        count_query = count_query.where(_ilike(Court.county, county))
    if court_type:
        query = query.where(Court.court_type == court_type)
        count_query = count_query.where(Court.court_type == court_type)
    # Tier lets the picker separate statewide/appellate forums (no county) from the
    # county-based trial courts -- the appellate courts are otherwise buried.
    if tier == "appellate":
        appellate = (
            CourtType.COURT_OF_CLAIMS, CourtType.COURT_OF_APPEALS, CourtType.SUPREME_COURT,
        )
        query = query.where(Court.court_type.in_(appellate))
        count_query = count_query.where(Court.court_type.in_(appellate))
    elif tier == "trial":
        trial = (
            CourtType.CIRCUIT, CourtType.DISTRICT, CourtType.PROBATE, CourtType.MUNICIPAL,
        )
        query = query.where(Court.court_type.in_(trial))
        count_query = count_query.where(Court.court_type.in_(trial))
    if q:
        cond = _ilike(Court.name, q) | _ilike(Court.city, q)
        query = query.where(cond)
        count_query = count_query.where(cond)
    if efiling_only:
        query = query.where(Court.is_efiling_enabled == True)  # noqa: E712
        count_query = count_query.where(Court.is_efiling_enabled == True)  # noqa: E712

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(Court.county, Court.name).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)

    return CourtListResponse(courts=list(result.scalars().all()), total=total)  # type: ignore[arg-type]


@router.get("/{court_id}", response_model=CourtResponse)
async def get_court(court_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Court).where(Court.id == court_id))
    court = result.scalar_one_or_none()
    if not court:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Court not found")
    return court


@router.get("/{court_id}/case-types", response_model=list[CaseTypeResponse])
async def list_case_types(court_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CaseType).where(CaseType.court_id == court_id, CaseType.is_active == True)  # noqa: E712
    )
    return list(result.scalars().all())


@router.get("/{court_id}/fee-schedules", response_model=list[FeeScheduleResponse])
async def list_fee_schedules(court_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FeeSchedule).where(
            FeeSchedule.court_id == court_id, FeeSchedule.is_active == True  # noqa: E712
        )
    )
    return list(result.scalars().all())
