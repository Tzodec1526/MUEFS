from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user_id
from app.database import get_db
from app.models.case import Case, CaseStatus
from app.models.filing import FilingEnvelope
from app.schemas.case import (
    CaseResponse,
    CaseSearchItemResponse,
    CaseSearchParticipantPublic,
    CaseSearchResponse,
)
from app.schemas.filing import FilingEnvelopeResponse
from app.services import access_service, search_service

router = APIRouter(prefix="/cases", tags=["Cases"])


def _to_search_item(case: Case) -> CaseSearchItemResponse:
    """Strip participant contact fields from search results (least-privilege listing)."""
    participants = [
        CaseSearchParticipantPublic(
            party_name=p.party_name,
            role=p.role,
            attorney_bar_number=p.attorney_bar_number,
        )
        for p in (case.participants or [])
    ]
    return CaseSearchItemResponse(
        id=case.id,
        court_id=case.court_id,
        case_number=case.case_number,
        case_type_id=case.case_type_id,
        title=case.title,
        status=case.status,
        filed_date=case.filed_date,
        judge_id=case.judge_id,
        created_at=case.created_at,
        is_sealed=case.is_sealed,
        participants=participants,
    )


@router.get("/search", response_model=CaseSearchResponse)
async def search_cases(
    case_number: str | None = None,
    party_name: str | None = None,
    attorney_bar_number: str | None = None,
    court_id: int | None = None,
    case_status: CaseStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user_id: int = Depends(get_current_user_id),
):
    """Court records search requires authentication; listing excludes contact PII."""
    cases, total = await search_service.search_cases(
        db,
        case_number=case_number,
        party_name=party_name,
        attorney_bar_number=attorney_bar_number,
        court_id=court_id,
        status=case_status,
        page=page,
        page_size=page_size,
    )
    return CaseSearchResponse(
        cases=[_to_search_item(c) for c in cases],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(Case).options(selectinload(Case.participants)).where(Case.id == case_id)
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if not await access_service.user_may_read_case(db, user_id, case_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this case",
        )
    return case


@router.get("/{case_id}/filings", response_model=list[FilingEnvelopeResponse])
async def get_case_filings(
    case_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    if not await access_service.user_may_read_case(db, user_id, case_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access filings for this case",
        )
    result = await db.execute(
        select(FilingEnvelope)
        .options(selectinload(FilingEnvelope.documents))
        .where(FilingEnvelope.case_id == case_id)
        .order_by(FilingEnvelope.created_at.desc())
    )
    ordered = list(result.scalars().all())
    visible = [
        env
        for env in ordered
        if await access_service.user_may_read_filing_envelope(db, user_id, env)
    ]
    start = (page - 1) * page_size
    return visible[start : start + page_size]
