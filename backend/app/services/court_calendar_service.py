from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.court_calendar import CourtCalendar
from app.models.user import CourtRole, UserCourtRole
from app.schemas.court_calendar import FilingDateAssessment


async def may_publish_calendar(db: AsyncSession, user_id: int | None, court_id: int) -> bool:
    if user_id is None:
        return False
    return bool(
        await db.scalar(
            select(UserCourtRole.id)
            .where(
                UserCourtRole.user_id == user_id,
                UserCourtRole.court_id == court_id,
                UserCourtRole.role.in_([CourtRole.ADMIN, CourtRole.JUDGE]),
            )
            .limit(1)
        )
    )


def assess_date(calendars: list[CourtCalendar], received_at: datetime) -> FilingDateAssessment:
    """MCR 1.109(G)(5)(b), using the newest published revision covering each day."""
    initial = next(
        (
            c
            for c in calendars
            if c.valid_from
            <= received_at.astimezone(ZoneInfo(c.timezone)).date()
            <= c.valid_through
        ),
        None,
    )
    result = FilingDateAssessment()
    if initial is None:
        result.error = "No published court calendar covers the received date"
        return result
    result.timezone = initial.timezone
    result.local_received_date = received_at.astimezone(ZoneInfo(initial.timezone)).date()
    day = result.local_received_date
    # Bounded even if a calendar closes every day. Do not infer an open day beyond coverage.
    for _ in range(367):
        calendar = next((c for c in calendars if c.valid_from <= day <= c.valid_through), None)
        if calendar is None or calendar.timezone != initial.timezone:
            result.error = (
                "Calendar coverage or timezone is unresolved before the next business day"
            )
            return result
        if calendar.id not in result.calendar_ids:
            result.calendar_ids.append(calendar.id)
        reason = calendar.closed_dates.get(day.isoformat())
        if reason is None and day.weekday() < 5:
            result.filing_date = day
            return result
        result.skipped_dates[day.isoformat()] = reason or "Weekend"
        day += timedelta(days=1)
    result.error = "No business day found within a year; court review is required"
    return result


async def filing_date_for_receipt(
    db: AsyncSession,
    court_id: int,
    received_at: datetime,
) -> FilingDateAssessment:
    utc_day: date = received_at.astimezone(UTC).date()
    # One query also covers a year boundary; adjacent published calendars may apply.
    calendars = list(
        await db.scalars(
            select(CourtCalendar)
            .where(
                CourtCalendar.court_id == court_id,
                CourtCalendar.valid_through >= utc_day - timedelta(days=1),
                CourtCalendar.valid_from <= utc_day + timedelta(days=367),
            )
            .order_by(CourtCalendar.id.desc())
        )
    )
    return assess_date(calendars, received_at)
