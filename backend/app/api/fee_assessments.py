"""Request and record itemized court fee assessments before payment or submission."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user_id, lock_current_user, require_user_may_manage_efilings
from app.database import get_db
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.user import User
from app.schemas.filing import FilingDocumentResponse, FilingEnvelopeResponse
from app.schemas.payment import (
    FeeAssessmentRequest,
    FeeReviewRequest,
    FilingFeeDetails,
    FilingFeeState,
)
from app.services import access_service, audit_service, filing_service
from app.services.fee_assessment_service import fee_state
from app.services.filing_record_service import record_transaction
from app.utils.http_context import client_ip, client_user_agent

router = APIRouter(tags=["Fee assessments"])


@router.get("/filings/{filing_id}/fees", response_model=FilingFeeDetails)
async def current_fees(
    filing_id: int,
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    # Document edits, assessments and payments all lock the envelope. Keep this
    # short read consistent so the reviewer's documents match the fee version.
    filing = await db.scalar(
        select(FilingEnvelope)
        .where(FilingEnvelope.id == filing_id)
        .options(selectinload(FilingEnvelope.documents))
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if filing is None:
        raise HTTPException(404, "Filing not found")
    if filing.filer_id != user_id and not await access_service.user_is_court_staff_for_court(
        db,
        user_id,
        filing.court_id,
    ):
        raise HTTPException(403, "Not authorized to view this filing's fees")
    fees = await fee_state(db, filing, user_id)
    return FilingFeeDetails(
        **fees.model_dump(), filing=FilingEnvelopeResponse.model_validate(filing)
    )


@router.post("/filings/{filing_id}/fee-review", response_model=FilingFeeState, status_code=201)
async def request_fee_review(
    filing_id: int,
    data: FeeReviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
    actor: User = Depends(require_user_may_manage_efilings),
):
    if not data.reason.strip():
        raise HTTPException(422, "Explain the requested fee review")
    async with db.begin_nested():
        await require_user_may_manage_efilings(await lock_current_user(db, actor.id))
        filing = await filing_service.get_filing(db, filing_id, for_update=True)
        if filing is None:
            raise HTTPException(404, "Filing not found")
        if filing.filer_id != actor.id:
            raise HTTPException(403, "Only the filer may request this fee review")
        fees = await fee_state(db, filing, actor.id)
        if not fees.can_request_review or filing.fee_version != data.expected_version:
            raise HTTPException(409, "This fee record changed. Refresh before requesting review")
        try:
            await filing_service.verify_filing_documents(filing)
        except filing_service.FilingDocumentError as exc:
            raise HTTPException(409, str(exc)) from exc
        now = datetime.now(UTC)
        claimed = await db.scalar(
            update(FilingEnvelope)
            .where(
                FilingEnvelope.id == filing.id,
                FilingEnvelope.fee_version == data.expected_version,
            )
            .values(fee_version=FilingEnvelope.fee_version + 1, fee_review_requested_at=now)
            .returning(FilingEnvelope.id)
        )
        if claimed is None:
            raise HTTPException(409, "This fee record changed. Refresh before requesting review")
        documents = [
            FilingDocumentResponse.model_validate(doc).model_dump(mode="json")
            for doc in filing.documents
        ]
        for doc in filing.documents:
            if doc.retained_at is None:
                doc.retained_at = now
        transaction = await record_transaction(
            db,
            filing,
            "fee_review_requested",
            actor.id,
            reason=data.reason.strip(),
            details={"documents": documents},
        )
        await audit_service.log_action(
            db,
            user_id=actor.id,
            action="fee_review_requested",
            entity_type="filing_envelope",
            entity_id=filing.id,
            details={"transaction_id": transaction.id},
            ip_address=client_ip(request),
            user_agent=client_user_agent(request),
        )
    return await fee_state(db, filing, actor.id)


@router.post("/clerk/filings/{filing_id}/fees", response_model=FilingFeeState, status_code=201)
async def assess_fees(
    filing_id: int,
    data: FeeAssessmentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    total = sum(item.amount_cents for item in data.items)
    if total > 100_000_000:
        raise HTTPException(422, "The assessment total exceeds the supported amount")
    async with db.begin_nested():
        await lock_current_user(db, user_id)
        filing = await filing_service.get_filing(db, filing_id, for_update=True)
        if filing is None:
            raise HTTPException(404, "Filing not found")
        if not await access_service.user_is_court_staff_for_court(db, user_id, filing.court_id):
            raise HTTPException(403, "Not authorized to assess fees for this court")
        if filing.filer_id == user_id:
            raise HTTPException(403, "Another court reviewer must assess fees for your own filing")
        fees = await fee_state(db, filing, user_id)
        if not fees.can_assess or filing.fee_version != data.expected_version:
            raise HTTPException(
                409, "This fee record changed or is governed by a waiver decision. Refresh it"
            )
        try:
            await filing_service.verify_filing_documents(filing)
        except filing_service.FilingDocumentError as exc:
            raise HTTPException(409, str(exc)) from exc
        claimed = await db.scalar(
            update(FilingEnvelope)
            .where(
                FilingEnvelope.id == filing.id,
                FilingEnvelope.fee_version == data.expected_version,
            )
            .values(fee_version=FilingEnvelope.fee_version + 1, fee_review_requested_at=None)
            .returning(FilingEnvelope.id)
        )
        if claimed is None:
            raise HTTPException(
                409, "This fee record changed. Refresh before recording an assessment"
            )
        now = datetime.now(UTC)
        documents = [
            FilingDocumentResponse.model_validate(doc).model_dump(mode="json")
            for doc in filing.documents
        ]
        for doc in filing.documents:
            if doc.retained_at is None:
                doc.retained_at = now
        transaction = await record_transaction(
            db,
            filing,
            "fee_assessed",
            user_id,
            reason=data.reason,
            details={
                "filing_version": data.expected_version + 1,
                "authority_reference": data.authority_reference,
                "items": [item.model_dump() for item in data.items],
                "total_cents": total,
                "previous_assessment_id": fees.assessment_id,
                "previous_total_cents": fees.total_cents,
                "documents": documents,
            },
        )
        filing.fee_assessment_id = transaction.id
        await audit_service.log_action(
            db,
            user_id=user_id,
            action="fee_assessed",
            entity_type="filing_envelope",
            entity_id=filing.id,
            details={"transaction_id": transaction.id},
            ip_address=client_ip(request),
            user_agent=client_user_agent(request),
        )
    return await fee_state(db, filing, user_id)


@router.get("/clerk/fee-reviews")
async def fee_review_queue(
    court_id: int = Query(...),
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    if not await access_service.user_is_court_staff_for_court(db, user_id, court_id):
        raise HTTPException(403, "Not authorized for this court")
    filters = (
        FilingEnvelope.court_id == court_id,
        FilingEnvelope.fee_review_requested_at.is_not(None),
        FilingEnvelope.status.not_in([FilingStatus.REJECTED, FilingStatus.SERVED]),
        FilingEnvelope.fee_waiver_requested.is_(False),
        FilingEnvelope.fee_waiver_granted.is_(None),
    )
    total = await db.scalar(select(func.count()).select_from(FilingEnvelope).where(*filters))
    rows = (
        await db.execute(
            select(FilingEnvelope, User.first_name, User.last_name)
            .join(
                User,
                User.id == FilingEnvelope.filer_id,
            )
            .where(*filters)
            .order_by(
                FilingEnvelope.fee_review_requested_at,
                FilingEnvelope.id,
            )
            .offset((page - 1) * 25)
            .limit(25)
        )
    ).all()
    return {
        "total": total or 0,
        "page": page,
        "filings": [
            {
                "id": filing.id,
                "case_title": filing.case_title,
                "status": filing.status,
                "filer_name": f"{first} {last}",
                "requested_at": filing.fee_review_requested_at.replace(
                    tzinfo=filing.fee_review_requested_at.tzinfo or UTC
                ).astimezone(UTC),
            }
            for filing, first, last in rows
            if filing.fee_review_requested_at is not None
        ],
    }
