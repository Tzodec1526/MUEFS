"""A reviewed derivative never overwrites the filed original or an earlier copy."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.retention import append_only


class DocumentPublicCopy(Base):
    __tablename__ = "document_public_copies"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("filing_documents.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(500))
    file_key: Mapped[str] = mapped_column(String(500))
    file_size_bytes: Mapped[int]
    mime_type: Mapped[str] = mapped_column(String(100), default="application/pdf")
    page_count: Mapped[int]
    sha256_hash: Mapped[str] = mapped_column(String(64))
    is_text_searchable: Mapped[bool]
    pii_warnings: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_document_public_copies_history", "document_id", "id"),)


append_only(DocumentPublicCopy.__table__)
