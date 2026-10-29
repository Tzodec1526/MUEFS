from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.auth import get_current_user_id, lock_current_user
from app.api.document_upload import store_document_upload
from app.api.params import RecordId
from app.database import get_db
from app.models.filing import FilingDocument, FilingEnvelope
from app.schemas.common import MAX_RECORD_ID
from app.schemas.filing import FilingDocumentResponse, FilingEnvelopeResponse
from app.services import access_service, audit_service, filing_service, storage_intent
from app.services.fee_waiver_service import waiver_state
from app.services.filing_record_service import record_transaction
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(prefix="/clerk/filings", tags=["Fee Waivers"])


async def _decidable_filing(
    db: AsyncSession, filing_id: int, user_id: int, action: str, expected_fee_version: int,
    *, for_update: bool,
) -> FilingEnvelope:
    filing = await filing_service.get_filing(db, filing_id, for_update=for_update)
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    if not await access_service.user_is_court_staff_for_court(db, user_id, filing.court_id):
        raise HTTPException(status_code=403, detail="Not authorized for this court")
    if not filing.fee_waiver_requested or filing.fee_waiver_granted is not None:
        raise HTTPException(status_code=409, detail="There is no undecided fee waiver request")
    state = await waiver_state(db, filing, user_id)
    if action not in state.allowed_actions:
        raise HTTPException(
            status_code=403,
            detail="This waiver action requires the appropriate court role and pending request",
        )
    # The filer may replace the application after the reviewer opened it.
    if filing.fee_version != expected_fee_version:
        raise HTTPException(
            status_code=409,
            detail="The fee waiver request changed. Refresh and review it before deciding",
        )
    return filing


@router.post("/{filing_id}/fee-waiver", response_model=FilingEnvelopeResponse)
async def decide_fee_waiver(
    request: Request,
    filing_id: RecordId,
    action: Literal[
        "grant_public_assistance",
        "grant_legal_services",
        "refer",
        "grant_judicial",
        "deny_judicial",
    ] = Form(...),
    reason: str = Form("", max_length=5000),
    amount_due_cents: int | None = Form(None, ge=0, le=100_000_000),
    expected_fee_version: int = Form(..., ge=0, le=MAX_RECORD_ID),
    file: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    await _decidable_filing(
        db, filing_id, user_id, action, expected_fee_version, for_update=False,
    )
    reason = reason.strip()
    if action == "deny_judicial" and (not reason or amount_due_cents is None):
        raise HTTPException(
            status_code=400, detail="Denial requires the order's reason and amount due"
        )
    if action != "refer" and file is None:
        raise HTTPException(
            status_code=400, detail="Attach the signed waiver or judicial order as a PDF"
        )
    if action == "refer" and file is not None:
        raise HTTPException(status_code=400, detail="Referral does not enter a court decision")

    # Screening the order can take many seconds, so store it before taking the locks
    # and repeat every check once they are held.
    doc = None
    if file is not None:
        doc = await store_document_upload(
            db, filing_id, file, "FEE_WAIVER_ORDER", "Signed fee waiver decision", True,
        )
    try:
        await lock_current_user(db, user_id)
        filing = await _decidable_filing(
            db, filing_id, user_id, action, expected_fee_version, for_update=True,
        )
        return await _record_decision(
            request, db, filing, user_id, action, reason, amount_due_cents, doc,
        )
    except Exception:
        if doc is not None:
            await run_in_threadpool(storage_intent.purge_keys, {doc.file_key})
        raise


async def _record_decision(
    request: Request,
    db: AsyncSession,
    filing: FilingEnvelope,
    user_id: int,
    action: str,
    reason: str,
    amount_due_cents: int | None,
    doc: FilingDocument | None,
) -> FilingEnvelope:
    now = datetime.now(UTC)
    filing.fee_version += 1
    filing.fee_review_requested_at = None
    details: dict = {"basis": action}
    if action == "refer":
        filing.fee_waiver_referred_at = now
        event = "waiver_referred"
    else:
        assert doc is not None
        db.add(doc)
        await db.flush()
        await db.refresh(doc)
        details["documents"] = [FilingDocumentResponse.model_validate(doc).model_dump(mode="json")]
        filing.fee_waiver_granted = action != "deny_judicial"
        filing.fee_waiver_decided_at = now
        filing.fee_waiver_amount_due_cents = 0 if filing.fee_waiver_granted else amount_due_cents
        details["amount_due_cents"] = filing.fee_waiver_amount_due_cents
        event = "waiver_granted" if filing.fee_waiver_granted else "waiver_denied"
    await record_transaction(db, filing, event, user_id, reason=reason, details=details)
    await audit_service.log_action(
        db,
        user_id=user_id,
        action=event,
        entity_type="filing_envelope",
        entity_id=filing.id,
        details={"basis": action},
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )
    await db.flush()
    await db.refresh(filing)
    await db.refresh(filing, ["documents"])
    return filing
