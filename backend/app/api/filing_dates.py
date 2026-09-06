"""Record dates established by signed court orders without altering receipt instants."""

from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.auth import get_current_user_id, lock_current_user
from app.api.document_upload import inspect_upload
from app.database import get_db
from app.models.case import Case
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.schemas.filing import FilingDocumentResponse
from app.services import access_service, audit_service, document_service
from app.services.filing_record_service import record_transaction
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(prefix="/clerk/filings", tags=["Filing dates"])


async def _date_filing(
    db: AsyncSession, user_id: int, filing_id: int, *, for_update: bool = False,
) -> FilingEnvelope:
    if for_update:
        await lock_current_user(db, user_id)
    query = select(FilingEnvelope).where(FilingEnvelope.id == filing_id)
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    filing = await db.scalar(query)
    if filing is None:
        raise HTTPException(404, "Filing not found")
    if not await access_service.user_is_court_staff_for_court(db, user_id, filing.court_id):
        raise HTTPException(403, "Not authorized for this court")
    return filing


def _order_block(filing: FilingEnvelope) -> str | None:
    if filing.filing_type == "service_only" or filing.status == FilingStatus.SERVED:
        return "Service-only records do not have a court filing date"
    if filing.status == FilingStatus.DRAFT:
        return "A court filing-date order can be recorded after submission"
    return None


@router.get("/{filing_id}/filing-date")
async def filing_date_state(
    filing_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    filing = await _date_filing(db, user_id, filing_id)
    case = await db.get(Case, filing.case_id) if filing.case_id else None
    return {
        "filing_id": filing.id,
        "court_id": filing.court_id,
        "status": filing.status,
        "submission_count": filing.submission_count,
        "submitted_at": (
            filing.submitted_at.replace(tzinfo=filing.submitted_at.tzinfo or UTC).astimezone(UTC)
            if filing.submitted_at else None
        ),
        "filing_date": filing.filing_date,
        "filing_date_basis": filing.filing_date_basis,
        "version": filing.filing_date_version,
        "case_id": filing.case_id,
        "case_number": case.case_number if case else None,
        "case_filing_date": case.filing_date if case else None,
        "case_date_version": case.filing_date_version if case else None,
        "order_block": _order_block(filing),
    }


@router.post("/{filing_id}/filing-date", status_code=201)
async def record_filing_date_order(
    filing_id: int,
    request: Request,
    filing_date: date = Form(...),
    order_signed_date: date = Form(...),
    authority_reference: str = Form(..., min_length=1, max_length=1000),
    reason: str = Form(..., min_length=1, max_length=5000),
    reviewed: bool = Form(...),
    expected_version: int = Form(..., ge=0),
    update_case_date: bool = Form(False),
    expected_case_version: int | None = Form(None, ge=0),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    authority_reference, reason = authority_reference.strip(), reason.strip()
    if not reviewed or not authority_reference or not reason:
        raise HTTPException(422, "Review the signed order and provide its reference and reason")
    if update_case_date and expected_case_version is None:
        raise HTTPException(422, "Refresh the case opening date before applying this order to it")
    filing = await _date_filing(db, user_id, filing_id)
    if blocked := _order_block(filing):
        raise HTTPException(409, blocked)
    if filing.filing_date_version != expected_version:
        raise HTTPException(409, "This filing changed. Refresh and review its date and status")

    # Inspect/store the PDF before acquiring authority and record locks. Recheck all
    # decisions after that slow work; revocation, resubmission and acceptance may race it.
    payload, mime, digest, inspection = await inspect_upload(file, require_pdf=True)
    file_key = f"filings/{filing_id}/orders/{uuid4()}.pdf"
    await run_in_threadpool(document_service.upload_document, payload, file_key, mime)
    try:
        async with db.begin_nested():
            filing = await _date_filing(db, user_id, filing_id, for_update=True)
            if blocked := _order_block(filing):
                raise HTTPException(409, blocked)
            if filing.filing_date_version != expected_version:
                raise HTTPException(
                    409, "This filing changed. Refresh and review its date and status",
                )

            previous_date = filing.filing_date.isoformat() if filing.filing_date else None
            details: dict = {
                "previous_filing_date": previous_date,
                "previous_filing_date_basis": filing.filing_date_basis,
            }
            if update_case_date:
                case = await db.scalar(select(Case).where(
                    Case.id == filing.case_id, Case.court_id == filing.court_id,
                ).with_for_update().execution_options(populate_existing=True))
                if case is None:
                    raise HTTPException(409, "There is no case opening date to update")
                details["case_date_change"] = {
                    "case_id": case.id,
                    "case_number": case.case_number,
                    "previous_filing_date": (
                        case.filing_date.isoformat() if case.filing_date else None
                    ),
                    "filing_date": filing_date.isoformat(),
                }
                changed_case = await db.scalar(update(Case).where(
                    Case.id == case.id, Case.filing_date_version == expected_case_version,
                ).values(
                    filing_date=filing_date, filing_date_version=Case.filing_date_version + 1,
                ).returning(Case.id))
                if changed_case is None:
                    raise HTTPException(409, "The case opening date changed. Refresh and review it")

            doc = FilingDocument(
                envelope_id=filing.id,
                document_type_code="FILING_DATE_ORDER",
                title=(f"Signed filing-date order — submission {filing.submission_count}"
                       if filing.submission_count else "Signed filing-date order — legacy filing"),
                file_key=file_key,
                file_size_bytes=len(payload),
                mime_type=mime,
                sha256_hash=digest,
                page_count=inspection.page_count,
                is_text_searchable=inspection.is_text_searchable,
                pii_warnings=inspection.pii_warnings,
                is_confidential=True,
                retained_at=datetime.now(UTC),
            )
            db.add(doc)
            await db.flush()
            basis = {
                "source": "court_order",
                "filing_date": filing_date.isoformat(),
                "order_document_id": doc.id,
                "order_signed_date": order_signed_date.isoformat(),
                "authority_reference": authority_reference,
                "submission_number": filing.submission_count,
            }
            changed = await db.scalar(update(FilingEnvelope).where(
                FilingEnvelope.id == filing.id,
                FilingEnvelope.filing_date_version == expected_version,
            ).values(
                filing_date=filing_date, filing_date_basis=basis,
                filing_date_version=FilingEnvelope.filing_date_version + 1,
            ).returning(FilingEnvelope.id))
            if changed is None:
                raise HTTPException(
                    409, "This filing changed. Refresh and review its date and status",
                )
            details.update(
                filing_date_basis=basis,
                documents=[FilingDocumentResponse.model_validate(doc).model_dump(mode="json")],
            )
            transaction = await record_transaction(
                db, filing, "filing_date_ordered", user_id, reason=reason, details=details,
            )
            await audit_service.log_action(
                db, user_id=user_id, action="filing_date_ordered", entity_type="filing_envelope",
                entity_id=filing.id,
                details={"transaction_id": transaction.id, "order_document_id": doc.id},
                ip_address=client_ip(request), user_agent=client_user_agent(request),
            )
    except Exception:
        await run_in_threadpool(document_service.delete_document, file_key)
        raise
    return {"transaction_id": transaction.id}
