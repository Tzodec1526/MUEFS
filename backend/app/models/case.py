import enum
from datetime import date, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.court import Court


class CaseStatus(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    DISMISSED = "dismissed"
    PENDING = "pending"


class ParticipantRole(enum.StrEnum):
    PLAINTIFF = "plaintiff"
    DEFENDANT = "defendant"
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    ATTORNEY_PLAINTIFF = "attorney_plaintiff"
    ATTORNEY_DEFENDANT = "attorney_defendant"
    ATTORNEY = "attorney"
    GUARDIAN = "guardian"
    INTERVENOR = "intervenor"


COUNSEL_ROLES = frozenset({
    ParticipantRole.ATTORNEY, ParticipantRole.ATTORNEY_PLAINTIFF,
    ParticipantRole.ATTORNEY_DEFENDANT,
})


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), index=True)
    case_number: Mapped[str] = mapped_column(String(50))
    case_type_id: Mapped[int] = mapped_column(ForeignKey("case_types.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    # Restricted docket access requires an explicit participant grant or court authority.
    is_sealed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus), default=CaseStatus.OPEN)
    filed_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    filing_date: Mapped[date | None]
    filing_date_version: Mapped[int] = mapped_column(default=0, server_default="0")
    judge_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    # Shared by participant grants and case-wide public access instructions.
    participant_version: Mapped[int] = mapped_column(default=0, server_default="0")

    __table_args__ = (
        sa.UniqueConstraint("court_id", "case_number", name="uq_case_court_number"),
        sa.Index("ix_cases_court_id_id", "court_id", "id"),
        sa.Index(
            "ix_cases_case_number_trgm", "case_number", postgresql_using="gin",
            postgresql_ops={"case_number": "public.gin_trgm_ops"},
        ).ddl_if(dialect="postgresql"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    court: Mapped["Court"] = relationship()
    participants: Mapped[list["CaseParticipant"]] = relationship(back_populates="case")


class CaseParticipant(Base):
    __tablename__ = "case_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[ParticipantRole] = mapped_column(Enum(ParticipantRole))
    party_name: Mapped[str] = mapped_column(String(255))
    attorney_bar_number: Mapped[str | None] = mapped_column(String(20), index=True)
    represented_party_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    access_enabled: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    contact_address: Mapped[str | None] = mapped_column(Text)

    case: Mapped["Case"] = relationship(back_populates="participants")

    __table_args__ = (
        sa.Index(
            "ix_case_participants_party_name_trgm", "party_name", postgresql_using="gin",
            postgresql_ops={"party_name": "public.gin_trgm_ops"},
        ).ddl_if(dialect="postgresql"),
    )
