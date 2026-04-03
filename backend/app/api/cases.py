from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_user_id
from app.database import get_db
from app.models.case import Case, CaseStatus
from app.models.filing import FilingEnvelope
from app.schemas.case import CaseResponse, CaseSearchResponse
from app.schemas.filing import FilingEnvelopeResponse
from app.services import search_service

router = APIRouter(prefix="/cases", tags=["Cases"])


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
):
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
    return CaseSearchResponse(cases=cases, total=total, page=page, page_size=page_size)  # type: ignore[arg-type]


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
    return case


@router.get("/{case_id}/filings", response_model=list[FilingEnvelopeResponse])
async def get_case_filings(
    case_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(FilingEnvelope)
        .options(selectinload(FilingEnvelope.documents))
        .where(FilingEnvelope.case_id == case_id)
        .order_by(FilingEnvelope.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all())
