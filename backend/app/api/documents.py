import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.database import get_db
from app.models.filing import FilingDocument
from app.schemas.document import DocumentVerifyResponse
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["Documents"])


def sanitize_filename(filename: str) -> str:
    """Remove path traversal and special characters from filenames."""
    filename = re.sub(r'[^\w\s\-.]', '', filename)
    filename = filename.strip('. ')
    return filename or "document"


@router.get("/{document_id}/download")
async def download_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(FilingDocument).where(FilingDocument.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Ownership check: verify user owns the filing or has a court role
    from app.models.filing import FilingEnvelope
    from app.models.user import CourtRole, UserCourtRole
    filing_result = await db.execute(
        select(FilingEnvelope).where(FilingEnvelope.id == doc.envelope_id)
    )
    filing = filing_result.scalar_one_or_none()
    if not filing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")

    is_owner = filing.filer_id == user_id
    is_court_staff = False
    if not is_owner:
        role_result = await db.execute(
            select(UserCourtRole).where(
                UserCourtRole.user_id == user_id,
                UserCourtRole.court_id == filing.court_id,
                UserCourtRole.role.in_([CourtRole.CLERK, CourtRole.JUDGE, CourtRole.ADMIN]),
            )
        )
        is_court_staff = role_result.scalar_one_or_none() is not None

    if not is_owner and not is_court_staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this document",
        )

    if doc.is_confidential and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: this document is sealed/confidential",
        )

    file_stream = await document_service.download_document(doc.file_key)
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
    user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(FilingDocument).where(FilingDocument.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Ownership check
    from app.models.filing import FilingEnvelope
    from app.models.user import CourtRole, UserCourtRole
    filing_result = await db.execute(
        select(FilingEnvelope).where(FilingEnvelope.id == doc.envelope_id)
    )
    filing = filing_result.scalar_one_or_none()
    if filing and filing.filer_id != user_id:
        role_result = await db.execute(
            select(UserCourtRole).where(
                UserCourtRole.user_id == user_id,
                UserCourtRole.court_id == filing.court_id,
                UserCourtRole.role.in_([CourtRole.CLERK, CourtRole.JUDGE, CourtRole.ADMIN]),
            )
        )
        if not role_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to verify this document",
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
