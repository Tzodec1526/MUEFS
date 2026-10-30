from datetime import datetime

from sqlalchemy import Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime


class StorageDeletion(Base):
    __tablename__ = "storage_deletions"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int]
    envelope_id: Mapped[int]
    file_key: Mapped[str] = mapped_column(String(500))
    queued_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    next_attempt_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(),
    )
    attempt_count: Mapped[int] = mapped_column(default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(250))

    __table_args__ = (Index("ix_storage_deletions_due", "next_attempt_at", "id"),)
