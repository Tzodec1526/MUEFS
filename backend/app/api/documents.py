import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_optional_user_id
from app.database import get_db
from app.models.filing import FilingDocument
from app.schemas.document import DocumentVerifyResponse
from app.services import access_service, audit_service, document_service
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(prefix="/documents", tags=["Documents"])


def sanitize_filename(filename: str) -> str:
    """Remove path traversal and special characters from filenames."""
    filename = re.sub(r'[^\w\s\-.]', '', filename)
    filename = filename.strip('. ')
    return filename or "document"


@router.get("/{document_id}/download")
async def download_document(
    request: Request,
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int | None = Depends(get_optional_user_id),
):
    """Public download for non-confidential documents on non-sealed, accepted/served
    filings. Confidential documents and sealed matters require an authorized account."""
    result = await db.execute(
        select(FilingDocument).where(FilingDocument.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if not await access_service.user_may_read_document(db, user_id, doc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this document",
        )

    await audit_service.log_action(
        db,
        user_id=user_id,
        action="document_download",
        entity_type="filing_document",
        entity_id=document_id,
        details=None,
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )

    try:
        file_stream = await document_service.download_document(doc.file_key)
    except (FileNotFoundError, OSError):
        # Seeded demo filings have a document record but no stored file behind it.
        # Show a clear message instead of a generic 500.
        return HTMLResponse(
            "<!doctype html><meta charset=\"utf-8\"><title>Simulated document</title>"
            "<div style=\"font-family:system-ui,-apple-system,sans-serif;max-width:30rem;"
            "margin:4rem auto;padding:2rem;text-align:center;color:#334155\">"
            "<h2 style=\"color:#1e3a5f;margin-bottom:0.5rem\">Simulated document</h2>"
            "<p>This is a demonstration filing &mdash; the document is simulated and is "
            "not available for download in the demo.</p></div>",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    safe_filename = sanitize_filename(doc.title)
    return StreamingResponse(
        file_stream,
        media_type=doc.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )


@router.get("/{document_id}/verify", response_model=DocumentVerifyResponse)
async def verify_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int | None = Depends(get_optional_user_id),
):
    result = await db.execute(
        select(FilingDocument).where(FilingDocument.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if not await access_service.user_may_read_document(db, user_id, doc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this document",
        )

    try:
        file_stream = await document_service.download_document(doc.file_key)
        file_data = file_stream.read()
        current_hash = document_service.compute_sha256(file_data)
        is_valid = current_hash == doc.sha256_hash
    except OSError:
        return DocumentVerifyResponse(
            document_id=document_id,
            sha256_hash=doc.sha256_hash,
            is_valid=False,
            message="Unable to verify document - file may be missing from storage",
        )

    return DocumentVerifyResponse(
        document_id=document_id,
        sha256_hash=doc.sha256_hash,
        is_valid=is_valid,
        message=(
            "Document integrity verified"
            if is_valid
            else "Document integrity check failed - hash mismatch"
        ),
    )
