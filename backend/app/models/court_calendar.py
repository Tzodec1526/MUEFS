"""Published court calendars are revisions, so receipt date calculations remain explainable."""

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.retention import append_only


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


append_only(CourtCalendar.__table__)
