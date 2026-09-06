import uuid
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.auth import get_current_user_id, lock_current_user, require_user_may_manage_efilings
from app.api.document_upload import store_document_upload
from app.database import get_db
from app.models.court import Court
from app.models.filing import COURT_DOCUMENT_TYPES, FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.user import User
from app.schemas.document import DocumentUploadResponse
from app.schemas.filing import (
    FilingEnvelopeCreate,
    FilingEnvelopeResponse,
    FilingEnvelopeUpdate,
    FilingHistoryResponse,
    FilingValidationResult,
    MyFilingsResponse,
)
from app.services import access_service, audit_service, document_service, filing_service
from app.services.fee_assessment_service import fee_state
from app.services.fee_waiver_service import waiver_state
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(prefix="/filings", tags=["Filings"])


@router.post("", response_model=FilingEnvelopeResponse, status_code=status.HTTP_201_CREATED)
async def create_filing(
    request: Request,
    data: FilingEnvelopeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_may_manage_efilings),
):
    user_id = current_user.id
    try:
        envelope = await filing_service.create_filing(db, user_id, data)
    except filing_service.FilingCreateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
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


@router.get("", response_model=MyFilingsResponse)
async def list_filings(
    status_filter: FilingStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    filings, total, status_counts = await filing_service.list_filings(
        db, user_id, status=status_filter, page=page, page_size=page_size
    )
    court_names = {}
    if filings:
        courts = await db.execute(
            select(Court.id, Court.name).where(Court.id.in_({f.court_id for f in filings}))
        )
        court_names = dict(courts.tuples().all())
    return MyFilingsResponse(
        filings=filings,  # type: ignore[arg-type]
        total=total, page=page, page_size=page_size,
        status_counts=status_counts, court_names=court_names,
    )


@router.get("/summary", response_model=dict[FilingStatus, int])
async def filing_summary(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    return await filing_service.get_filing_status_counts(db, user_id)


@router.get("/{filing_id}", response_model=FilingEnvelopeResponse)
async def get_filing(
    filing_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    filing = await filing_service.get_filing(db, filing_id)
    if not filing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")
    # The full envelope contains the fee-waiver application. Case access uses the
    # separately filtered docket endpoint, not this private filing record.
    if filing.filer_id != user_id and not await access_service.user_is_court_staff_for_court(
        db, user_id, filing.court_id,
    ):
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
    current_user: User = Depends(require_user_may_manage_efilings),
):
    user_id = current_user.id
    filing = await filing_service.get_filing(db, filing_id, for_update=True)
    if not filing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")
    if filing.filer_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your filing")
    if filing.status not in (FilingStatus.DRAFT, FilingStatus.RETURNED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only update draft or returned filings",
        )

    if filing.submitted_at is not None and (
        (data.fee_waiver_requested is not None
         and data.fee_waiver_requested != filing.fee_waiver_requested)
        or (data.fee_waiver_reason is not None
            and data.fee_waiver_reason != filing.fee_waiver_reason)
    ):
        raise HTTPException(
            status_code=409,
            detail="A submitted fee waiver request cannot be changed through draft editing",
        )

    if data.case_title is not None:
        filing.case_title = data.case_title
    if data.filing_description is not None:
        filing.filing_description = data.filing_description
    if data.fee_waiver_requested is not None:
        filing.fee_waiver_requested = data.fee_waiver_requested
        if data.fee_waiver_requested:
            filing.fee_review_requested_at = None
    if data.fee_waiver_reason is not None:
        filing.fee_waiver_reason = data.fee_waiver_reason

    await db.flush()
    await db.refresh(filing)
    await db.refresh(filing, ["documents"])
    return filing


@router.post("/{filing_id}/validate", response_model=FilingValidationResult)
async def validate_filing(
    filing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_may_manage_efilings),
):
    user_id = current_user.id
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
    current_user: User = Depends(require_user_may_manage_efilings),
    idempotency_key: uuid.UUID | None = Header(None),
):
    user_id = current_user.id
    # Ownership check
    await require_user_may_manage_efilings(await lock_current_user(db, user_id))
    filing_check = await filing_service.get_filing(db, filing_id, for_update=True)
    if not filing_check:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")
    if filing_check.filer_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this filing",
        )

    if idempotency_key and await db.scalar(select(FilingTransaction.id).where(
        FilingTransaction.filing_id == filing_id,
        FilingTransaction.idempotency_key == str(idempotency_key),
    )):
        return filing_check
    if filing_check.status not in (FilingStatus.DRAFT, FilingStatus.RETURNED):
        raise HTTPException(
            status_code=400, detail="Only draft or returned filings can be submitted",
        )

    if not (await fee_state(db, filing_check)).obligation_met:
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

    try:
        filing = await filing_service.submit_filing(
            db, filing_id, idempotency_key=str(idempotency_key) if idempotency_key else None,
        )
    except filing_service.FilingDocumentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not filing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft or returned filings can be submitted",
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
    current_user: User = Depends(require_user_may_manage_efilings),
):
    user_id = current_user.id
    filing = await filing_service.get_filing(db, filing_id, for_update=True)
    if not filing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")
    if filing.filer_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your filing")
    if filing.status not in (FilingStatus.DRAFT, FilingStatus.RETURNED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot upload documents to this filing",
        )

    if document_type_code in COURT_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=403, detail="Court decisions must be recorded by authorized court staff",
        )
    doc, pii_warnings = await store_document_upload(
        db, filing_id, file, document_type_code, title, is_confidential,
    )
    try:
        filing.fee_version += 1
        await audit_service.log_action(
            db, user_id=user_id, action="upload_document", entity_type="filing_document",
            entity_id=doc.id, details={"filing_id": filing_id, "filename": file.filename},
            ip_address=client_ip(request), user_agent=client_user_agent(request),
        )
    except Exception:
        await run_in_threadpool(document_service.delete_document, doc.file_key)
        raise
    return DocumentUploadResponse(
        id=doc.id, title=doc.title, file_size_bytes=doc.file_size_bytes,
        mime_type=doc.mime_type, sha256_hash=doc.sha256_hash,
        is_text_searchable=doc.is_text_searchable, page_count=doc.page_count,
        warnings=pii_warnings,
    )


@router.delete("/{filing_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document(
    request: Request,
    filing_id: int,
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user_may_manage_efilings),
):
    user_id = current_user.id
    filing = await filing_service.get_filing(db, filing_id, for_update=True)
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

    filing.fee_version += 1

    if doc.retained_at is not None or filing.submitted_at is not None:
        # Corrections remove a document from the next submission, not from history.
        doc.removed_at = datetime.now(UTC)
        await db.flush()
    else:
        file_key = doc.file_key
        await db.delete(doc)
        await db.flush()
        await run_in_threadpool(document_service.delete_document, file_key)

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


@router.get("/{filing_id}/history", response_model=FilingHistoryResponse)
async def filing_history(
    filing_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    filing = await db.get(FilingEnvelope, filing_id)
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    # Receipts include rejected submissions, private document metadata, and payment
    # references. Standing on the public/sealed case alone does not grant this access.
    staff = await access_service.user_is_court_staff_for_court(db, user_id, filing.court_id)
    if filing.filer_id != user_id and not staff:
        raise HTTPException(
            status_code=403, detail="Only the filer and court staff can view receipts",
        )
    query = select(FilingTransaction).where(FilingTransaction.filing_id == filing_id)
    transactions = await db.scalars(query.order_by(
        FilingTransaction.occurred_at.desc(), FilingTransaction.id.desc(),
    ).offset((page - 1) * page_size).limit(page_size))
    total = await db.scalar(select(func.count()).select_from(FilingTransaction).where(
        FilingTransaction.filing_id == filing_id,
    )) or 0
    return FilingHistoryResponse(
        filing_id=filing.id, status=filing.status, submission_count=filing.submission_count,
        transactions=list(transactions),  # type: ignore[arg-type]
        total=total, page=page, page_size=page_size,
        fee_waiver=await waiver_state(db, filing, user_id) if filing.fee_waiver_requested else None,
        filing_date=filing.filing_date, filing_date_basis=filing.filing_date_basis,
        court_id=filing.court_id,
        can_manage_documents=staff,
    )
