from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.database import get_db
from app.models.filing import FilingStatus
from app.schemas.filing import (
    BatchReviewRequest,
    ClerkReviewRequest,
    FilingEnvelopeResponse,
    FilingListResponse,
)
from app.services import access_service, audit_service, filing_service
from app.utils.http_context import client_ip, client_user_agent

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


@router.get("/queue", response_model=FilingListResponse)
async def get_review_queue(
    court_id: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status_filter: FilingStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    await _require_clerk_role(db, user_id, court_id)
    if status_filter not in (None, FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW):
        raise HTTPException(
            status_code=400, detail="Queue status must be submitted or under_review"
        )
    filings, total = await filing_service.get_clerk_queue(
        db, court_id, page=page, page_size=page_size, status=status_filter
    )
    return FilingListResponse(filings=filings, total=total, page=page, page_size=page_size)  # type: ignore[arg-type]


@router.post("/filings/{filing_id}/review", response_model=FilingEnvelopeResponse)
async def review_filing(
    request: Request,
    filing_id: int,
    data: ClerkReviewRequest,
    db: AsyncSession = Depends(get_db),
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
    filing_check = await filing_service.get_filing(db, filing_id)
    if not filing_check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found"
        )
    await _require_clerk_role(db, user_id, filing_check.court_id)

    try:
        filing = await filing_service.review_filing(
            db, filing_id, reviewer_id=user_id, action=data.action, reason=reason
        )
    except filing_service.CmsSubmissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Court CMS rejected the filing: {exc.detail}",
        ) from exc
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
    db: AsyncSession = Depends(get_db),
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

    results: dict[str, list[int]] = {"succeeded": [], "failed": []}
    for fid in dict.fromkeys(data.filing_ids):
        try:
            # One failure must roll back that filing's case, receipt, and notices,
            # without poisoning the transaction for the rest of the batch.
            async with db.begin_nested():
                filing_check = await filing_service.get_filing(db, fid)
                if not filing_check:
                    results["failed"].append(fid)
                    continue
                await _require_clerk_role(db, user_id, filing_check.court_id)
                f = await filing_service.review_filing(
                    db, fid, reviewer_id=user_id, action=data.action
                )
                succeeded = f is not None and f.status == FilingStatus.ACCEPTED
            results["succeeded" if succeeded else "failed"].append(fid)
        except Exception:
            results["failed"].append(fid)

    await audit_service.log_action(
        db,
        user_id=user_id,
        action="batch_review_accept",
        entity_type="filing_envelope",
        entity_id=0,
        details={"succeeded": len(results["succeeded"]), "failed": len(results["failed"])},
        ip_address=client_ip(request),
        user_agent=client_user_agent(request),
    )
    return results
