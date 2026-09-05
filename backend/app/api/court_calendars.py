from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id, get_optional_user_id
from app.database import get_db
from app.models.court import Court
from app.models.court_calendar import CourtCalendar
from app.schemas.court_calendar import (
    CourtCalendarCreate,
    CourtCalendarResponse,
    CourtCalendarsResponse,
    FilingDateAssessment,
)
from app.services import audit_service
from app.services.court_calendar_service import filing_date_for_receipt, may_publish_calendar
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(prefix="/courts", tags=["Court Calendars"])


@router.get("/{court_id}/calendars", response_model=CourtCalendarsResponse)
async def calendars(
    court_id: int,
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    user_id: int | None = Depends(get_optional_user_id),
):
    if not await db.get(Court, court_id):
        raise HTTPException(status_code=404, detail="Court not found")
    rows = list(
        await db.scalars(
            select(CourtCalendar)
            .where(CourtCalendar.court_id == court_id)
            .order_by(CourtCalendar.id.desc())
            .offset((page - 1) * 25)
            .limit(25)
        )
    )
    total = (
        await db.scalar(
            select(func.count())
            .select_from(CourtCalendar)
            .where(CourtCalendar.court_id == court_id)
        )
        or 0
    )
    return CourtCalendarsResponse(
        calendars=[CourtCalendarResponse.model_validate(row) for row in rows],
        total=total,
        can_publish=await may_publish_calendar(db, user_id, court_id),
    )


@router.post("/{court_id}/calendars", response_model=CourtCalendarResponse, status_code=201)
async def publish_calendar(
    request: Request,
    court_id: int,
    data: CourtCalendarCreate,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    if not await may_publish_calendar(db, user_id, court_id):
        raise HTTPException(
            status_code=403, detail="Court administrator or judge assignment required"
        )
    calendar = CourtCalendar(
        court_id=court_id,
        **data.model_dump(exclude={"closed_dates"}),
        closed_dates={day.isoformat(): reason for day, reason in data.closed_dates.items()},
        published_by=user_id,
        published_at=datetime.now(UTC),
    )
    db.add(calendar)
    await db.flush()
    await audit_service.log_action(
        db,
        user_id=user_id,
        action="publish_court_calendar",
        entity_type="court_calendar",
        entity_id=calendar.id,
        details=data.model_dump(mode="json"),
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )
    return calendar


@router.get("/{court_id}/filing-date", response_model=FilingDateAssessment)
async def preview_filing_date(
    court_id: int,
    received_at: datetime,
    db: AsyncSession = Depends(get_db),
):
    if received_at.tzinfo is None:
        raise HTTPException(
            status_code=400, detail="Include a UTC offset in the received timestamp"
        )
    if not await db.get(Court, court_id):
        raise HTTPException(status_code=404, detail="Court not found")
    return await filing_date_for_receipt(db, court_id, received_at)
