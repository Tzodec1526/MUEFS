"""Document storage + parsing.

S3/MinIO calls go through ``starlette.concurrency.run_in_threadpool`` because
``boto3`` is synchronous; otherwise large uploads/downloads would block the
FastAPI event loop and stall every other concurrent request.

PDF parsing for the upload pipeline is consolidated into ``parse_pdf_metadata``
so we read a PDF once and extract page count + searchability + (optional) PII
hits in a single pass. ``filing_service.validate_filing`` previously re-parsed
every PDF a second time during validation; that is now O(1) per document.
"""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.utils.pdf import check_pii_patterns

logger = logging.getLogger(__name__)


def _is_demo_mode() -> bool:
    """Check if running in demo mode (SQLite / no S3)."""
    return "sqlite" in settings.database_url


def _local_storage_path() -> Path:
    """Get local document storage directory for demo mode."""
    p = Path("demo_uploads")
    p.mkdir(exist_ok=True)
    return p


def get_s3_client():
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def detect_mime_type(file_data: bytes) -> str:
    """Detect MIME type from file content using python-magic."""
    try:
        import magic
        return magic.from_buffer(file_data[:2048], mime=True)
    except Exception:
        return "application/octet-stream"


def compute_sha256(file_data: bytes) -> str:
    return hashlib.sha256(file_data).hexdigest()


def validate_file_size(file_size: int) -> bool:
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    return file_size <= max_bytes


_ALLOWED_MIME_TYPES = frozenset({
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "application/rtf",
    "image/tiff",
    "image/jpeg",
    "image/png",
})


def validate_mime_type(mime_type: str) -> bool:
    return mime_type in _ALLOWED_MIME_TYPES


def _safe_local_path(file_key: str) -> Path:
    """Resolve local path and verify it stays within the storage directory."""
    base = _local_storage_path().resolve()
    local_path = (base / file_key).resolve()
    if not local_path.is_relative_to(base):
        raise ValueError("Invalid file key: path traversal detected")
    return local_path


async def upload_document(
    file_data: bytes,
    file_key: str,
    content_type: str,
) -> str:
    if _is_demo_mode():
        local_path = _safe_local_path(file_key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(file_data)
        return file_key

    def _upload() -> None:
        client = get_s3_client()
        client.upload_fileobj(
            io.BytesIO(file_data),
            settings.s3_bucket_name,
            file_key,
            ExtraArgs={"ContentType": content_type},
        )

    await run_in_threadpool(_upload)
    return file_key


async def download_document(file_key: str) -> BinaryIO:
    if _is_demo_mode():
        local_path = _safe_local_path(file_key)
        return io.BytesIO(local_path.read_bytes())

    def _download() -> BinaryIO:
        client = get_s3_client()
        response = client.get_object(Bucket=settings.s3_bucket_name, Key=file_key)
        return response["Body"]

    return await run_in_threadpool(_download)


async def delete_document(file_key: str) -> None:
    if _is_demo_mode():
        local_path = _safe_local_path(file_key)
        if local_path.exists():
            local_path.unlink()
        return

    def _delete() -> None:
        client = get_s3_client()
        client.delete_object(Bucket=settings.s3_bucket_name, Key=file_key)

    await run_in_threadpool(_delete)


@dataclass
class PdfMetadata:
    """One-shot result of inspecting an uploaded PDF."""

    page_count: int | None = None
    is_text_searchable: bool = False
    pii_warnings: list[str] = field(default_factory=list)


def parse_pdf_metadata(
    file_data: bytes,
    *,
    pii_scan_pages: int = 0,
) -> PdfMetadata:
    """Extract page count + searchability + (optional) PII hits in a single PDF parse.

    ``pii_scan_pages > 0`` walks at most that many pages looking for SSNs / DOBs /
    account numbers and stops at the first hit. Pass 0 (the default) at upload time
    when only the cheap fields are needed.
    """
    meta = PdfMetadata()
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_data))
    except Exception as exc:
        logger.warning("Failed to open PDF for inspection: %s", exc)
        return meta

    try:
        meta.page_count = len(reader.pages)
    except Exception as exc:
        logger.warning("Failed to read PDF page count: %s", exc)

    if not meta.page_count:
        return meta

    try:
        first_text = reader.pages[0].extract_text() or ""
    except Exception as exc:
        logger.warning("Failed to extract first PDF page text: %s", exc)
        first_text = ""
    meta.is_text_searchable = bool(first_text.strip())

    if pii_scan_pages > 0 and meta.is_text_searchable:
        # Re-use first page's text; only re-extract more pages if no hit yet.
        if first_text:
            hits = check_pii_patterns(first_text)
            if hits:
                meta.pii_warnings.extend(hits)
        if not meta.pii_warnings:
            for page in reader.pages[1 : pii_scan_pages]:
                try:
                    text = page.extract_text() or ""
                except Exception:
                    continue
                hits = check_pii_patterns(text)
                if hits:
                    meta.pii_warnings.extend(hits)
                    break
    return meta


def get_pdf_page_count(file_data: bytes) -> int | None:
    """Back-compat wrapper around :func:`parse_pdf_metadata`."""
    return parse_pdf_metadata(file_data).page_count


def is_pdf_text_searchable(file_data: bytes) -> bool:
    """Back-compat wrapper around :func:`parse_pdf_metadata`."""
    return parse_pdf_metadata(file_data).is_text_searchable
