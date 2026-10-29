import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id, lock_current_user
from app.api.params import Page, RecordId
from app.database import get_db
from app.models.filing import FilingEnvelope, FilingStatus
from app.schemas.common import MAX_RECORD_ID
from app.schemas.filing import (
    BatchReviewRequest,
    ClerkQueueResponse,
    ClerkReviewRequest,
    FilingEnvelopeResponse,
)
from app.services import access_service, audit_service, filing_service
from app.utils.http_context import client_ip, client_user_agent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clerk", tags=["Clerk Review"])


async def _require_clerk_role(
    db: AsyncSession, user_id: int, court_id: int,
) -> None:
    """Verify user has clerk/judge/admin role for the given court."""
    if not await access_service.user_is_court_staff_for_court(db, user_id, court_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized as clerk for this court",
        )


async def _require_independent_reviewer(
    db: AsyncSession, user_id: int, filing: FilingEnvelope,
) -> None:
    """Like fee assessments and waivers, a filer cannot decide their own filing."""
    await _require_clerk_role(db, user_id, filing.court_id)
    if filing.filer_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Another court reviewer must decide your own filing",
        )


@router.get("/queue", response_model=ClerkQueueResponse)
async def get_review_queue(
    court_id: int = Query(ge=1, le=MAX_RECORD_ID),
    page: Page = 1,
    page_size: int = Query(25, ge=1, le=100),
    status_filter: FilingStatus | None = Query(None, alias="status"),
    fee_waivers: bool = Query(False),
    search: str = Query("", max_length=200),
    waiting_48h_only: bool = Query(False),
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    await _require_clerk_role(db, user_id, court_id)
    if status_filter not in (None, FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW):
        raise HTTPException(
            status_code=400, detail="Queue status must be submitted or under_review"
        )
    return await filing_service.get_clerk_queue(
        db, court_id, page=page, page_size=page_size, status=status_filter, fee_waivers=fee_waivers,
        search=search, waiting_48h_only=waiting_48h_only,
    )


@router.post("/filings/{filing_id}/review", response_model=FilingEnvelopeResponse)
async def review_filing(
    request: Request,
    filing_id: RecordId,
    data: ClerkReviewRequest,
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    if data.action not in ("accept", "reject", "return"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be 'accept', 'reject', or 'return'",
        )

    reason = data.reason.strip() if data.reason else None
    if data.action in ("reject", "return") and not reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reason is required for reject/return actions",
        )

    # Look up filing to check court authorization
    await lock_current_user(db, user_id)
    filing_check = await filing_service.get_filing(db, filing_id)
    if not filing_check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found"
        )
    await _require_independent_reviewer(db, user_id, filing_check)

    try:
        filing = await filing_service.review_filing(
            db,
            filing_id,
            reviewer_id=user_id,
            action=data.action,
            reason=reason,
            expected_submission_count=data.expected_submission_count,
        )
    except (
        filing_service.FilingDestinationError,
        filing_service.StaleFilingReviewError,
        filing_service.FilingDateUnavailableError,
        filing_service.FilingDocumentError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not filing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filing cannot be reviewed (not in submitted/under_review status)",
        )
    if data.action == "accept" and filing.status != FilingStatus.ACCEPTED:
        # Return 502 without raising so get_db commits cms_error on the envelope.
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "detail": (
                    f"Court CMS rejected the filing: "
                    f"{filing.cms_error or 'CMS submission failed'}"
                )
            },
        )
    await db.refresh(filing)
    await db.refresh(filing, ["documents"])

    await audit_service.log_action(
        db,
        user_id=user_id,
        action=f"review_filing_{data.action}",
        entity_type="filing_envelope",
        entity_id=filing_id,
        details={"action": data.action, "reason": data.reason},
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )

    return filing


@router.post("/queue/batch-review")
async def batch_review_filings(
    request: Request,
    data: BatchReviewRequest,
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int = Depends(get_current_user_id),
):
    """Batch accept filings (UI multi-select).
    Rejects/returns remain single-file (reasons required per item).
    """
    if data.action != "accept":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Batch review currently supports only 'accept' "
                "(per-item reasons required for reject/return)"
            ),
        )

    await lock_current_user(db, user_id)
    succeeded: list[int] = []
    failed: list[int] = []
    errors: dict[int, str] = {}
    # Different reviewers must acquire envelope locks in the same order.
    for item in sorted(data.filings, key=lambda item: item.filing_id):
        fid = item.filing_id
        failure = "The filing is no longer awaiting review. Refresh the queue."
        try:
            # One failure must roll back that filing's case, receipt, and notices,
            # without poisoning the transaction for the rest of the batch.
            async with db.begin_nested():
                filing_check = await filing_service.get_filing(db, fid)
                f = None
                if filing_check:
                    await _require_independent_reviewer(db, user_id, filing_check)
                    f = await filing_service.review_filing(
                        db,
                        fid,
                        reviewer_id=user_id,
                        action=data.action,
                        expected_submission_count=item.expected_submission_count,
                    )
            if f is not None and f.status == FilingStatus.ACCEPTED:
                succeeded.append(fid)
                continue
            if f is not None and f.cms_error:
                failure = "Court CMS submission failed. Open the filing to inspect its history."
        except (
            filing_service.FilingDestinationError,
            filing_service.StaleFilingReviewError,
            filing_service.FilingDateUnavailableError,
            filing_service.FilingDocumentError,
        ) as exc:
            failure = str(exc)
        except HTTPException as exc:
            failure = str(exc.detail)
        except Exception:
            logger.exception("Batch acceptance of filing %s failed", fid)
            failure = "Could not accept this filing. Open it for review."
        failed.append(fid)
        errors[fid] = failure

    await audit_service.log_action(
        db,
        user_id=user_id,
        action="batch_review_accept",
        entity_type="filing_envelope",
        entity_id=0,
        details={"succeeded": len(succeeded), "failed": len(failed)},
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )
    return {"succeeded": succeeded, "failed": failed, "errors": errors}
