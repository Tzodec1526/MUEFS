import enum
import hashlib
import json
from datetime import date, datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

PRIVATE_DOCUMENT_TYPES = frozenset({"FEE_WAIVER", "FEE_WAIVER_ORDER"})
COURT_DOCUMENT_TYPES = frozenset({"FEE_WAIVER_ORDER", "FILING_DATE_ORDER"})


class FilingStatus(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RETURNED = "returned"
    SERVED = "served"  # Legacy API/storage value: documents recorded, not proof of delivery.


class FilingType(enum.StrEnum):
    INITIAL = "initial"          # New case initiation
    SUBSEQUENT = "subsequent"    # Filing to existing case
    SERVICE_ONLY = "service_only"  # Record documents for service outside clerk intake.


class FilingEnvelope(Base):
    __tablename__ = "filing_envelopes"

    @property
    def details_token(self) -> str:
        """Identify the editable details and submission the filer actually opened."""
        values = [
            self.id, self.status, self.submission_count,
            self.case_title, self.filing_description,
        ]
        return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode("utf-8")).hexdigest()

    @property
    def submission_token(self) -> str:
        """Bind final review to the details, active documents, and fee state."""
        values = [
            self.details_token, self.court_id, self.case_id, self.case_type_id,
            self.filing_type, self.fee_version, self.payment_id,
            self.fee_waiver_requested, self.fee_waiver_granted,
            self.fee_waiver_reason, self.fee_waiver_amount_due_cents,
            [
                [doc.id, doc.document_type_code, doc.title, doc.sha256_hash,
                 doc.file_size_bytes, doc.mime_type, doc.page_count,
                 doc.is_confidential, doc.is_text_searchable]
                for doc in sorted(self.documents, key=lambda doc: doc.id)
            ],
        ]
        return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode("utf-8")).hexdigest()

    id: Mapped[int] = mapped_column(primary_key=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), index=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), index=True)
    case_type_id: Mapped[int] = mapped_column(ForeignKey("case_types.id"), index=True)
    filer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    creation_key: Mapped[str | None] = mapped_column(String(36))
    creation_sha256: Mapped[str | None] = mapped_column(String(64))
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
    fee_waiver_requested: Mapped[bool] = mapped_column(default=False)
    fee_waiver_granted: Mapped[bool | None] = mapped_column(default=None)
    fee_waiver_reason: Mapped[str | None] = mapped_column(String(2000))
    fee_waiver_referred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fee_waiver_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fee_waiver_amount_due_cents: Mapped[int | None] = mapped_column(Integer)
    cms_case_number: Mapped[str | None] = mapped_column(String(100))
    cms_filing_id: Mapped[str | None] = mapped_column(String(100))
    cms_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    submission_count: Mapped[int] = mapped_column(default=0, server_default="0")
    filing_date: Mapped[date | None]
    filing_date_basis: Mapped[dict | None] = mapped_column(JSON)
    filing_date_version: Mapped[int] = mapped_column(default=0, server_default="0")
    fee_version: Mapped[int] = mapped_column(default=0, server_default="0")
    fee_review_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fee_assessment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey(
        "filing_transactions.id", use_alter=True, name="fk_filing_fee_assessment",
    ))

    documents: Mapped[list["FilingDocument"]] = relationship(
        back_populates="envelope",
        primaryjoin="and_(FilingEnvelope.id == FilingDocument.envelope_id, "
        "FilingDocument.removed_at.is_(None), "
        "FilingDocument.document_type_code.not_in(('FEE_WAIVER_ORDER', 'FILING_DATE_ORDER')))",
        order_by="FilingDocument.id",
    )

    __table_args__ = (
        Index('uq_filing_creation_key', 'filer_id', 'creation_key', unique=True,
              postgresql_where=text('creation_key IS NOT NULL'),
              sqlite_where=text('creation_key IS NOT NULL')),
        # Status is covered for counters; updated_at/id support stable page ordering.
        Index('ix_filing_filer_updated', 'filer_id', 'updated_at', 'id', 'status'),
        Index('ix_filing_pending_received', 'court_id', 'submitted_at', 'id', 'status',
              postgresql_where=text("status IN ('SUBMITTED', 'UNDER_REVIEW')"),
              sqlite_where=text("status IN ('SUBMITTED', 'UNDER_REVIEW')")),
        Index('ix_filing_court_status_submitted', 'court_id', 'status', 'submitted_at'),
        Index('ix_filing_court_waiver', 'court_id', 'fee_waiver_requested',
              'fee_waiver_granted', 'submitted_at'),
        Index('ix_filing_court_fee_review', 'court_id', 'fee_review_requested_at', 'id'),
    )


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
    pii_warnings: Mapped[list[str] | None] = mapped_column(JSON)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    retained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    access_version: Mapped[int] = mapped_column(default=0, server_default="0")
    public_copy_id: Mapped[int | None] = mapped_column(ForeignKey(
        "document_public_copies.id", use_alter=True, name="fk_document_public_copy",
    ))

    envelope: Mapped["FilingEnvelope"] = relationship(back_populates="documents")
