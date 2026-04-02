import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CourtType(str, enum.Enum):
    CIRCUIT = "circuit"
    DISTRICT = "district"
    PROBATE = "probate"
    COURT_OF_APPEALS = "court_of_appeals"
    SUPREME_COURT = "supreme_court"
    MUNICIPAL = "municipal"


class CaseCategory(str, enum.Enum):
    CIVIL = "civil"
    CRIMINAL = "criminal"
    FAMILY = "family"
    PROBATE = "probate"
    TRAFFIC = "traffic"
    SMALL_CLAIMS = "small_claims"
    APPEALS = "appeals"


class Court(Base):
    __tablename__ = "courts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    county: Mapped[str] = mapped_column(String(100), index=True)
    court_type: Mapped[CourtType] = mapped_column(Enum(CourtType), index=True)
    division: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(2), default="MI")
    zip_code: Mapped[str | None] = mapped_column(String(10))
    phone: Mapped[str | None] = mapped_column(String(20))
    cms_type: Mapped[str | None] = mapped_column(String(50))  # JIS, Tyler, etc.
    is_efiling_enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    case_types: Mapped[list["CaseType"]] = relationship(back_populates="court")
    fee_schedules: Mapped[list["FeeSchedule"]] = relationship(back_populates="court")
    filing_requirements: Mapped[list["FilingRequirement"]] = relationship(back_populates="court")
    filing_checklists: Mapped[list["FilingChecklist"]] = relationship(back_populates="court")


class CaseType(Base):
    __tablename__ = "case_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[CaseCategory] = mapped_column(Enum(CaseCategory))
    filing_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)

    court: Mapped["Court"] = relationship(back_populates="case_types")


class FeeSchedule(Base):
    __tablename__ = "fee_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), index=True)
    case_type_id: Mapped[int | None] = mapped_column(ForeignKey("case_types.id"), index=True)
    fee_type: Mapped[str] = mapped_column(String(100))
    amount_cents: Mapped[int] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(default=True)

    court: Mapped["Court"] = relationship(back_populates="fee_schedules")


class FilingRequirement(Base):
    __tablename__ = "filing_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), index=True)
    case_type_id: Mapped[int | None] = mapped_column(ForeignKey("case_types.id"), index=True)
    document_type_code: Mapped[str] = mapped_column(String(50))
    is_required: Mapped[bool] = mapped_column(default=True)
    description: Mapped[str] = mapped_column(Text)
    mcr_reference: Mapped[str | None] = mapped_column(String(50))  # e.g., "MCR 2.116"
    local_rule_reference: Mapped[str | None] = mapped_column(String(100))
    page_limit: Mapped[int | None] = mapped_column(Integer)
    format_notes: Mapped[str | None] = mapped_column(Text)

    court: Mapped["Court"] = relationship(back_populates="filing_requirements")


class FilingChecklist(Base):
    __tablename__ = "filing_checklists"

    id: Mapped[int] = mapped_column(primary_key=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), index=True)
    case_type_id: Mapped[int | None] = mapped_column(ForeignKey("case_types.id"), index=True)
    motion_type: Mapped[str] = mapped_column(String(100))
    checklist_items: Mapped[dict] = mapped_column(JSON, default=dict)
    help_text: Mapped[str | None] = mapped_column(Text)
    mcr_url: Mapped[str | None] = mapped_column(String(500))

    court: Mapped["Court"] = relationship(back_populates="filing_checklists")
