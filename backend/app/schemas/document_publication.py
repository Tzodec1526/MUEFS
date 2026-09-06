from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class PublicCopyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_id: int
    title: str
    file_size_bytes: int
    mime_type: str
    page_count: int
    sha256_hash: str
    is_text_searchable: bool
    pii_warnings: list[str]
    created_at: datetime

    @field_serializer("created_at")
    def utc_created_at(self, value: datetime) -> str:
        return value.replace(tzinfo=value.tzinfo or UTC).isoformat()


class WithholdDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=2000)


class PublishCopy(WithholdDocument):
    copy_id: int = Field(ge=1)
    reviewed: Literal[True]
