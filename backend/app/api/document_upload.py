"""The common bounded, inspected upload path for filer documents and court orders."""

import hashlib
import re
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.models.filing import PRIVATE_DOCUMENT_TYPES, FilingDocument
from app.services import document_service
from app.utils import malware_scan


async def inspect_upload(
    file: UploadFile,
    *, require_pdf: bool = False,
) -> tuple[bytes, str, str, document_service.PdfInspection]:
    # Bound the read without retaining both a chunk list and a joined copy.
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    file_data = await file.read(max_bytes + 1)
    if len(file_data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_file_size_mb}MB",
        )

    # Validate MIME type from file content (never trust client Content-Type alone).
    try:
        content_type = await run_in_threadpool(
            document_service.resolve_upload_mime_type, file_data, file.content_type
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    if not document_service.validate_mime_type(content_type):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Accepted: PDF, Word, TXT, RTF, TIFF, JPG, PNG",
        )

    if require_pdf and content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="This document must be a PDF")

    # Malware screening (defense in depth): reject executables / known-bad signatures
    # regardless of the declared MIME type.
    try:
        scan = await malware_scan.scan_upload(file_data)
    except malware_scan.ScannerUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Malware screening is temporarily unavailable. "
                   "Your document was not uploaded. Please retry shortly.",
            headers={"Retry-After": "30"},
        ) from exc
    if not scan.is_clean:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=scan.reason or "File rejected by malware screening",
        )

    sha256 = (await run_in_threadpool(hashlib.sha256, file_data)).hexdigest()
    inspection = document_service.PdfInspection()
    if content_type == "application/pdf":
        inspection = await run_in_threadpool(document_service.inspect_pdf, file_data)
        if not inspection.page_count:
            raise HTTPException(status_code=422, detail="The document must be a readable PDF")
    return file_data, content_type, sha256, inspection


async def store_document_upload(
    db: AsyncSession,
    filing_id: int,
    file: UploadFile,
    document_type_code: str,
    title: str,
    is_confidential: bool = False,
) -> tuple[FilingDocument, list[str]]:
    file_data, content_type, sha256, inspection = await inspect_upload(
        file, require_pdf=document_type_code == "FEE_WAIVER_ORDER",
    )
    safe_name = re.sub(r"[^\w\s\-.]", "", file.filename or "document") or "document"
    file_key = f"filings/{filing_id}/{uuid.uuid4()}/{safe_name}"
    await run_in_threadpool(document_service.upload_document, file_data, file_key, content_type)

    try:
        doc = FilingDocument(
            envelope_id=filing_id,
            document_type_code=document_type_code,
            title=title,
            file_key=file_key,
            file_size_bytes=len(file_data),
            mime_type=content_type,
            page_count=inspection.page_count,
            sha256_hash=sha256,
            is_confidential=(
                is_confidential or document_type_code in PRIVATE_DOCUMENT_TYPES
            ),
            retained_at=datetime.now(UTC) if document_type_code == "FEE_WAIVER_ORDER" else None,
            is_text_searchable=inspection.is_text_searchable,
            pii_warnings=inspection.pii_warnings,
        )
        db.add(doc)
        await db.flush()
        await db.refresh(doc)
    except Exception:
        await run_in_threadpool(document_service.delete_document, file_key)
        raise
    return doc, inspection.pii_warnings
