from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user_id
from app.database import get_db
from app.models.court import Court
from app.models.user import CourtRole, UserCourtRole
from app.schemas.filing import ClerkReviewRequest, FilingEnvelopeResponse, FilingListResponse
from app.services import audit_service, filing_service, notification_service

router = APIRouter(prefix="/clerk", tags=["Clerk Review"])


async def _require_clerk_role(
    db: AsyncSession, user_id: int, court_id: int,
) -> None:
    """Verify user has clerk/judge/admin role for the given court."""
    result = await db.execute(
        select(UserCourtRole).where(
            UserCourtRole.user_id == user_id,
            UserCourtRole.court_id == court_id,
            UserCourtRole.role.in_([CourtRole.CLERK, CourtRole.JUDGE, CourtRole.ADMIN]),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized as clerk for this court",
        )


@router.get("/queue", response_model=FilingListResponse)
async def get_review_queue(
    court_id: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    await _require_clerk_role(db, user_id, court_id)
    filings, total = await filing_service.get_clerk_queue(
        db, court_id, page=page, page_size=page_size
    )
    return FilingListResponse(filings=filings, total=total, page=page, page_size=page_size)  # type: ignore[arg-type]


@router.post("/filings/{filing_id}/review", response_model=FilingEnvelopeResponse)
async def review_filing(
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

    if data.action in ("reject", "return") and not data.reason:
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

    filing = await filing_service.review_filing(
        db, filing_id, reviewer_id=user_id, action=data.action, reason=data.reason
    )
    if not filing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filing cannot be reviewed (not in submitted/under_review status)",
        )
    await db.refresh(filing)
    await db.refresh(filing, ["documents"])

    await audit_service.log_action(
        db, user_id=user_id, action=f"review_filing_{data.action}",
        entity_type="filing_envelope", entity_id=filing_id,
        details={"action": data.action, "reason": data.reason},
    )

    # Look up actual court name for notification
    court_result = await db.execute(select(Court).where(Court.id == filing.court_id))
    court = court_result.scalar_one_or_none()
    court_name = court.name if court else f"Court #{filing.court_id}"

    status_text = "returned" if data.action == "return" else data.action + "ed"
    await notification_service.notify_filing_status_change(
        db,
        filer_id=filing.filer_id,
        filing_id=filing_id,
        status=status_text,
        court_name=court_name,
        case_title=filing.case_title,
        reason=data.reason,
    )

    return filing
