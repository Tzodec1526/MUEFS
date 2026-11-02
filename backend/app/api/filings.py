import hashlib
import json
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
    Response,
    UploadFile,
    status,
)
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.api.auth import get_current_user_id, lock_current_user, require_user_may_manage_efilings
from app.api.document_upload import read_upload, store_document_upload
from app.api.params import Page, RecordId
from app.database import get_db
from app.models.court import Court
from app.models.filing import (
    COURT_DOCUMENT_TYPES,
    DocumentUploadRequest,
    FilingDocument,
    FilingEnvelope,
    FilingStatus,
)
from app.models.filing_transaction import FilingTransaction
from app.models.storage_deletion import StorageDeletion
from app.models.user import User
from app.schemas.document import DocumentUploadResponse
from app.schemas.filing import (
    FilingEnvelopeCreate,
    FilingEnvelopeResponse,
    FilingEnvelopeUpdate,
    FilingHistoryResponse,
    FilingSubmitRequest,
    FilingTransactionResponse,
    FilingValidationResult,
    MyFilingsResponse,
)
from app.services import (
    access_service,
    audit_service,
    document_service,
    filing_service,
    storage_intent,
)
from app.services.fee_waiver_service import waiver_state
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(prefix="/filings", tags=["Filings"])


async def _owned_filing(
    db: AsyncSession,
    filing_id: int,
    user_id: int,
    *,
    for_update: bool = False,
    refusal: str = "Not your filing",
) -> FilingEnvelope:
    filing = await filing_service.get_filing(db, filing_id, for_update=for_update)
    if not filing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")
    if filing.filer_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=refusal)
    return filing


def _upload_response(doc: FilingDocument) -> DocumentUploadResponse:
    return DocumentUploadResponse(
        id=doc.id, title=doc.title, file_size_bytes=doc.file_size_bytes,
        mime_type=doc.mime_type, sha256_hash=doc.sha256_hash,
        is_text_searchable=doc.is_text_searchable, page_count=doc.page_count,
        warnings=doc.pii_warnings or [],
    )


@router.post(
    "", response_model=FilingEnvelopeResponse, status_code=status.HTTP_201_CREATED,
    responses={200: {"model": FilingEnvelopeResponse, "description": "Existing creation request"}},
)
async def create_filing(
    request: Request,
    response: Response,
    data: FilingEnvelopeCreate,
    idempotency_key: uuid.UUID = Header(alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(require_user_may_manage_efilings),
):
    current_user = await require_user_may_manage_efilings(
        await lock_current_user(db, current_user.id),
    )
    user_id = current_user.id
    key = str(idempotency_key)
    query = select(FilingEnvelope).where(
        FilingEnvelope.filer_id == user_id, FilingEnvelope.creation_key == key,
    ).options(selectinload(FilingEnvelope.documents)).execution_options(populate_existing=True)
    envelope = await db.scalar(query)
    created = False
    if envelope is None:
        try:
            async with db.begin_nested():
                envelope = await filing_service.create_filing(db, user_id, data, creation_key=key)
            created = True
        except (IntegrityError, filing_service.FilingDestinationError) as exc:
            envelope = await db.scalar(query)
            if envelope is None:
                if isinstance(exc, filing_service.FilingDestinationError):
                    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
                raise
    if not created:
        if envelope.creation_sha256 != filing_service.creation_fingerprint(data):
            return JSONResponse(status_code=409, content={
                "detail": "An earlier save created this filing with different details. "
                          "Open it and compare your edits before saving again.",
                "filing_id": envelope.id,
            })
        response.status_code = status.HTTP_200_OK
        return envelope
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
    page: Page = 1,
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db, scope="function"),
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
        court_names = {court_id: name for court_id, name in courts}
    return MyFilingsResponse(
        filings=filings,
        total=total, page=page, page_size=page_size,
        status_counts=status_counts, court_names=court_names,
    )


@router.get("/summary", response_model=dict[FilingStatus, int])
async def filing_summary(
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    return await filing_service.get_filing_status_counts(db, user_id)


@router.get("/{filing_id}", response_model=FilingEnvelopeResponse)
async def get_filing(
    filing_id: RecordId,
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    filing = await filing_service.get_filing(db, filing_id)
    if not filing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")
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
    filing_id: RecordId,
    data: FilingEnvelopeUpdate,
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(require_user_may_manage_efilings),
):
    filing = await _owned_filing(db, filing_id, current_user.id, for_update=True)
    try:
        return await filing_service.update_details(db, filing, data)
    except filing_service.FilingUpdateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/{filing_id}/validate", response_model=FilingValidationResult)
async def validate_filing(
    filing_id: RecordId,
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(require_user_may_manage_efilings),
):
    user_id = current_user.id
    filing = await _owned_filing(
        db, filing_id, user_id, refusal="Not authorized to access this filing",
    )
    try:
        await filing_service.validate_filing_destination(db, filing, filer_id=user_id)
    except filing_service.FilingDestinationError as exc:
        return FilingValidationResult(is_valid=False, errors=[exc.detail])
    return await filing_service.validate_filing(db, filing)


@router.post("/{filing_id}/submit", response_model=FilingEnvelopeResponse)
async def submit_filing(
    request: Request,
    filing_id: RecordId,
    data: FilingSubmitRequest,
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(require_user_may_manage_efilings),
    idempotency_key: uuid.UUID | None = Header(None),
):
    user_id = current_user.id
    await require_user_may_manage_efilings(await lock_current_user(db, user_id))
    await _owned_filing(db, filing_id, user_id, refusal="Not authorized to access this filing")

    try:
        filing = await filing_service.submit_filing(
            db, filing_id, idempotency_key=str(idempotency_key) if idempotency_key else None,
            expected_submission_token=data.expected_submission_token,
        )
    except filing_service.SubmissionAlreadyRecordedError as exc:
        return exc.filing
    except (
        filing_service.FilingDestinationError, filing_service.FilingSubmissionError,
    ) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except filing_service.FilingDocumentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not filing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft or returned filings can be submitted",
        )
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
    filing_id: RecordId,
    idempotency_key: uuid.UUID = Header(alias="Idempotency-Key"),
    file: UploadFile = File(...),
    document_type_code: str = Form(..., min_length=1, max_length=50, pattern=r"\S"),
    title: str = Form(..., min_length=1, max_length=500, pattern=r"\S"),
    is_confidential: bool = Form(False),
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(require_user_may_manage_efilings),
):
    user_id = current_user.id
    filing = await _owned_filing(db, filing_id, user_id)

    def fingerprint(sha256: str, size: int) -> str:
        fields = [document_type_code, title, is_confidential,
                  file.filename, file.content_type, size, sha256]
        return hashlib.sha256(json.dumps(fields, separators=(",", ":")).encode()).hexdigest()

    async def replay(recorded: DocumentUploadRequest, digest: str, size: int):
        if recorded.fingerprint != fingerprint(digest, size):
            raise HTTPException(status_code=409, detail=(
                "This upload request key was already used for a different document. "
                "Review the saved filing before starting another upload."
            ))
        doc = await db.get(FilingDocument, recorded.document_id) if recorded.document_id else None
        if doc is None or doc.removed_at is not None:
            raise HTTPException(status_code=409, detail=(
                "This document was already uploaded and later removed. "
                "Review the saved filing before starting another upload."
            ))
        return _upload_response(doc)

    key = str(idempotency_key)
    recorded = await db.get(DocumentUploadRequest, (filing_id, key))
    if recorded:
        content = await read_upload(file)
        digest = (await run_in_threadpool(hashlib.sha256, content)).hexdigest()
        return await replay(recorded, digest, len(content))

    if filing.status not in (FilingStatus.DRAFT, FilingStatus.RETURNED):
        raise HTTPException(status_code=400, detail="Cannot upload documents to this filing")
    if document_type_code in COURT_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=403,
            detail="Court decisions must be recorded by authorized court staff",
        )
    doc = await store_document_upload(
        db, filing_id, file, document_type_code, title, is_confidential,
    )
    try:
        await require_user_may_manage_efilings(await lock_current_user(db, user_id))
        locked = await filing_service.get_filing(db, filing_id, for_update=True)
        if not locked or locked.filer_id != user_id:
            raise HTTPException(status_code=403, detail="Not your filing")
        recorded = await db.get(DocumentUploadRequest, (filing_id, key), populate_existing=True)
        if recorded:
            response = await replay(recorded, doc.sha256_hash, doc.file_size_bytes)
            await run_in_threadpool(document_service.delete_document, doc.file_key)
            storage_intent.release_upload(db.sync_session, doc.file_key)
            return response
        if locked.status not in (FilingStatus.DRAFT, FilingStatus.RETURNED):
            raise HTTPException(status_code=400, detail="Cannot upload documents to this filing")
        db.add(doc)
        await db.flush()
        db.add(DocumentUploadRequest(
            envelope_id=filing_id, key=key, document_id=doc.id,
            fingerprint=fingerprint(doc.sha256_hash, doc.file_size_bytes),
        ))
        locked.fee_version += 1
        await audit_service.log_action(
            db, user_id=user_id, action="upload_document", entity_type="filing_document",
            entity_id=doc.id, details={"filing_id": filing_id, "filename": file.filename},
            ip_address=client_ip(request), user_agent=client_user_agent(request),
        )
    except Exception:
        await run_in_threadpool(storage_intent.purge_keys, {doc.file_key})
        raise
    return _upload_response(doc)


@router.delete("/{filing_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document(
    request: Request,
    filing_id: RecordId,
    document_id: RecordId,
    db: AsyncSession = Depends(get_db, scope="function"),
    current_user: User = Depends(require_user_may_manage_efilings),
):
    user_id = current_user.id
    filing = await _owned_filing(db, filing_id, user_id, for_update=True)

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
        doc.removed_at = datetime.now(UTC)
        await db.flush()
    else:
        await db.execute(update(DocumentUploadRequest).where(
            DocumentUploadRequest.document_id == doc.id,
        ).values(document_id=None))
        db.add(StorageDeletion(
            document_id=doc.id, envelope_id=filing_id, file_key=doc.file_key,
        ))
        storage_intent.track_deletion(db.sync_session)
        await db.delete(doc)
        await db.flush()

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
    filing_id: RecordId,
    page: Page = 1,
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    filing = await db.get(FilingEnvelope, filing_id)
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
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
        transactions=[FilingTransactionResponse.model_validate(row) for row in transactions],
        total=total, page=page, page_size=page_size,
        fee_waiver=await waiver_state(db, filing, user_id) if filing.fee_waiver_requested else None,
        filing_date=filing.filing_date, filing_date_basis=filing.filing_date_basis,
        court_id=filing.court_id,
        can_manage_documents=staff and filing.filer_id != user_id,
    )
