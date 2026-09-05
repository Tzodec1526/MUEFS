"""Published court calendars are revisions, so receipt date calculations remain explainable."""

from datetime import date, datetime

from sqlalchemy import DDL, JSON, Date, DateTime, ForeignKey, Index, String, event
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CourtCalendar(Base):
    __tablename__ = "court_calendars"

    id: Mapped[int] = mapped_column(primary_key=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"))
    timezone: Mapped[str] = mapped_column(String(64))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_through: Mapped[date] = mapped_column(Date)
    closed_dates: Mapped[dict] = mapped_column(JSON)
    authority_reference: Mapped[str] = mapped_column(String(1000))
    published_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_calendar_court_coverage", "court_id", "valid_through", "id"),)


for operation in ("UPDATE", "DELETE"):
    event.listen(
        CourtCalendar.__table__,
        "after_create",
        DDL(f"""
        CREATE TRIGGER court_calendars_no_{operation.lower()}
        BEFORE {operation} ON court_calendars
        BEGIN SELECT RAISE(ABORT, 'court_calendars is append-only'); END
    """).execute_if(dialect="sqlite"),
    )
event.listen(
    CourtCalendar.__table__,
    "after_create",
    DDL("""
    CREATE FUNCTION protect_court_calendars() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'court_calendars is append-only'; END; $$
""").execute_if(dialect="postgresql"),
)
event.listen(
    CourtCalendar.__table__,
    "after_create",
    DDL("""
    CREATE TRIGGER court_calendars_append_only BEFORE UPDATE OR DELETE ON court_calendars
    FOR EACH ROW EXECUTE FUNCTION protect_court_calendars()
""").execute_if(dialect="postgresql"),
)
event.listen(
    CourtCalendar.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS protect_court_calendars()").execute_if(dialect="postgresql"),
)
