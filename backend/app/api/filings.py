import re
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.config import settings
from app.database import get_db
from app.models.filing import FilingDocument, FilingStatus
from app.schemas.document import DocumentUploadResponse
from app.schemas.filing import (
    FilingEnvelopeCreate,
    FilingEnvelopeResponse,
    FilingEnvelopeUpdate,
    FilingListResponse,
    FilingValidationResult,
)
from app.services import access_service, audit_service, document_service, filing_service
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(prefix="/filings", tags=["Filings"])


@router.post("", response_model=FilingEnvelopeResponse, status_code=status.HTTP_201_CREATED)
async def create_filing(
    request: Request,
    data: FilingEnvelopeCreate,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    envelope = await filing_service.create_filing(db, user_id, data)
    await audit_service.log_action(
        db,
        user_id=user_id,
        action="create_filing",
        entity_type="filing_envelope",
        entity_id=envelope.id,
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )
    return envelope


@router.get("", response_model=FilingListResponse)
async def list_filings(
    status_filter: FilingStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    filings, total = await filing_service.list_filings(
        db, user_id, status=status_filter, page=page, page_size=page_size
    )
    return FilingListResponse(filings=filings, total=total, page=page, page_size=page_size)  # type: ignore[arg-type]


@router.get("/{filing_id}", response_model=FilingEnvelopeResponse)
async def get_filing(
    filing_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    filing = await filing_service.get_filing(db, filing_id)
    if not filing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")
    if not await access_service.user_may_read_filing_envelope(db, user_id, filing):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this filing",
        )
    return filing


@router.patch("/{filing_id}", response_model=FilingEnvelopeResponse)
async def update_filing(
    filing_id: int,
    data: FilingEnvelopeUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    filing = await filing_service.get_filing(db, filing_id)
    if not filing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")
    if filing.filer_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your filing")
    if filing.status != FilingStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only update draft filings",
        )

    if data.case_title is not None:
        filing.case_title = data.case_title
    if data.filing_description is not None:
        filing.filing_description = data.filing_description

    await db.flush()
    await db.refresh(filing)
    await db.refresh(filing, ["documents"])
    return filing


@router.post("/{filing_id}/validate", response_model=FilingValidationResult)
async def validate_filing(
    filing_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    filing = await filing_service.get_filing(db, filing_id)
    if not filing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")
    if filing.filer_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this filing",
        )
    return await filing_service.validate_filing(db, filing_id)


@router.post("/{filing_id}/submit", response_model=FilingEnvelopeResponse)
async def submit_filing(
    request: Request,
    filing_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    # Ownership check
    filing_check = await filing_service.get_filing(db, filing_id)
    if not filing_check:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")
    if filing_check.filer_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this filing",
        )

    # Verify payment for non-service-only, non-fee-waiver filings
    if (
        filing_check.filing_type != "service_only"
        and not filing_check.fee_waiver_requested
        and filing_check.payment_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Payment required before submission",
        )

    # Validate before submitting
    validation = await filing_service.validate_filing(db, filing_id)
    if not validation.is_valid:
        error_parts = []
        if validation.errors:
            error_parts.append("Errors: " + "; ".join(validation.errors))
        if validation.missing_required_documents:
            error_parts.append(
                "Missing documents: " + "; ".join(validation.missing_required_documents)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filing validation failed. " + " | ".join(error_parts),
        )

    filing = await filing_service.submit_filing(db, filing_id)
    if not filing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filing cannot be submitted (not in draft status)",
        )
    # Full refresh to get updated_at, then load documents relationship
    await db.refresh(filing)
    await db.refresh(filing, ["documents"])

    await audit_service.log_action(
        db,
        user_id=user_id,
        action="submit_filing",
        entity_type="filing_envelope",
        entity_id=filing_id,
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )
    return filing


@router.post("/{filing_id}/documents", response_model=DocumentUploadResponse)
async def upload_document(
    request: Request,
    filing_id: int,
    file: UploadFile = File(...),
    document_type_code: str = Form(...),
    title: str = Form(...),
    is_confidential: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    filing = await filing_service.get_filing(db, filing_id)
    if not filing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")
    if filing.filer_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your filing")
    if filing.status not in (FilingStatus.DRAFT, FilingStatus.RETURNED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot upload documents to this filing",
        )

    # Read file in chunks to prevent memory exhaustion from spoofed Content-Length
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    chunks: list[bytes] = []
    total_read = 0
    while True:
        chunk = await file.read(65536)  # 64KB chunks
        if not chunk:
            break
        total_read += len(chunk)
        if total_read > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum size of {settings.max_file_size_mb}MB",
            )
        chunks.append(chunk)
    file_data = b"".join(chunks)

    # Validate MIME type: try content detection first, fall back to HTTP header
    detected_type = document_service.detect_mime_type(file_data)
    http_type = file.content_type or "application/octet-stream"
    # Use detected type if it's specific, otherwise trust the HTTP header
    content_type = detected_type if detected_type != "application/octet-stream" else http_type
    if not document_service.validate_mime_type(content_type):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Accepted: PDF, Word, TXT, RTF, TIFF, JPG, PNG",
        )

    sha256 = document_service.compute_sha256(file_data)
    safe_name = re.sub(r'[^\w\s\-.]', '', file.filename or 'document') or 'document'
    file_key = f"filings/{filing_id}/{uuid.uuid4()}/{safe_name}"

    await document_service.upload_document(file_data, file_key, content_type)

    page_count = None
    is_searchable = False
    if content_type == "application/pdf":
        page_count = document_service.get_pdf_page_count(file_data)
        is_searchable = document_service.is_pdf_text_searchable(file_data)

    try:
        doc = FilingDocument(
            envelope_id=filing_id,
            document_type_code=document_type_code,
            title=title,
            file_key=file_key,
            file_size_bytes=len(file_data),
            mime_type=content_type,
            page_count=page_count,
            sha256_hash=sha256,
            is_confidential=is_confidential,
            is_text_searchable=is_searchable,
        )
        db.add(doc)
        await db.flush()
        await db.refresh(doc)

        await audit_service.log_action(
            db,
            user_id=user_id,
            action="upload_document",
            entity_type="filing_document",
            entity_id=doc.id,
            details={"filing_id": filing_id, "filename": file.filename},
            ip_address=client_ip(request),
            user_agent=client_user_agent(request),
        )
    except Exception:
        # Clean up orphaned S3 object if DB operations fail
        await document_service.delete_document(file_key)
        raise

    return DocumentUploadResponse(
        id=doc.id,
        title=doc.title,
        file_size_bytes=doc.file_size_bytes,
        mime_type=doc.mime_type,
        sha256_hash=doc.sha256_hash,
        is_text_searchable=doc.is_text_searchable,
        page_count=doc.page_count,
    )


@router.delete("/{filing_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document(
    request: Request,
    filing_id: int,
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    filing = await filing_service.get_filing(db, filing_id)
    if not filing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")
    if filing.filer_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your filing")

    # Record immutability: only draft/returned envelopes may drop attachments (court retention).
    if filing.status not in (FilingStatus.DRAFT, FilingStatus.RETURNED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Submitted filings cannot be altered by removing documents",
        )

    doc = next((d for d in filing.documents if d.id == document_id), None)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Delete from DB first, then storage — if DB fails, storage is intact
    file_key = doc.file_key
    await db.delete(doc)
    await db.flush()
    await document_service.delete_document(file_key)

    await audit_service.log_action(
        db,
        user_id=user_id,
        action="remove_document",
        entity_type="filing_document",
        entity_id=document_id,
        details={"filing_id": filing_id},
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )
