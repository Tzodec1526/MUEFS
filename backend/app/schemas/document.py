from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: int
    title: str
    file_size_bytes: int
    mime_type: str
    sha256_hash: str
    is_text_searchable: bool
    page_count: int | None


class DocumentVerifyResponse(BaseModel):
    document_id: int
    sha256_hash: str
    is_valid: bool
    message: str
