import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CaseStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    DISMISSED = "dismissed"
    PENDING = "pending"


class ParticipantRole(str, enum.Enum):
    PLAINTIFF = "plaintiff"
    DEFENDANT = "defendant"
    PETITIONER = "petitioner"
    RESPONDENT = "respondent"
    ATTORNEY_PLAINTIFF = "attorney_plaintiff"
    ATTORNEY_DEFENDANT = "attorney_defendant"
    GUARDIAN = "guardian"
    INTERVENOR = "intervenor"


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), index=True)
    case_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    case_type_id: Mapped[int] = mapped_column(ForeignKey("case_types.id"))
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus), default=CaseStatus.OPEN)
    filed_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    judge_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    participants: Mapped[list["CaseParticipant"]] = relationship(back_populates="case")


class CaseParticipant(Base):
    __tablename__ = "case_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    role: Mapped[ParticipantRole] = mapped_column(Enum(ParticipantRole))
    party_name: Mapped[str] = mapped_column(String(255))
    attorney_bar_number: Mapped[str | None] = mapped_column(String(20))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    contact_address: Mapped[str | None] = mapped_column(Text)

    case: Mapped["Case"] = relationship(back_populates="participants")
