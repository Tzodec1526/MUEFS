import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FilingStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RETURNED = "returned"
    SERVED = "served"  # Service-only filings go straight to served


class FilingType(str, enum.Enum):
    INITIAL = "initial"          # New case initiation
    SUBSEQUENT = "subsequent"    # Filing to existing case
    SERVICE_ONLY = "service_only"  # Serve on parties, not filed with court


class FilingEnvelope(Base):
    __tablename__ = "filing_envelopes"

    id: Mapped[int] = mapped_column(primary_key=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), index=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), index=True)
    case_type_id: Mapped[int] = mapped_column(ForeignKey("case_types.id"), index=True)
    filer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    filing_type: Mapped[str] = mapped_column(String(20), default="subsequent")
    status: Mapped[FilingStatus] = mapped_column(
        Enum(FilingStatus), default=FilingStatus.DRAFT, index=True
    )
    case_title: Mapped[str | None] = mapped_column(String(500))
    filing_description: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list["FilingDocument"]] = relationship(back_populates="envelope")


class FilingDocument(Base):
    __tablename__ = "filing_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    envelope_id: Mapped[int] = mapped_column(ForeignKey("filing_envelopes.id"), index=True)
    document_type_code: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(500))
    file_key: Mapped[str] = mapped_column(String(500))  # S3 path
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(100))
    page_count: Mapped[int | None] = mapped_column(Integer)
    sha256_hash: Mapped[str] = mapped_column(String(64))
    is_confidential: Mapped[bool] = mapped_column(default=False)
    is_text_searchable: Mapped[bool] = mapped_column(default=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    envelope: Mapped["FilingEnvelope"] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document")


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    filing_document_id: Mapped[int] = mapped_column(
        ForeignKey("filing_documents.id"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    file_key: Mapped[str] = mapped_column(String(500))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    sha256_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    document: Mapped["FilingDocument"] = relationship(back_populates="versions")
