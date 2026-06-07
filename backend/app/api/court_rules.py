from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.court import FilingChecklist, FilingRequirement
from app.schemas.court import FilingChecklistResponse, FilingRequirementResponse
from app.services.filing_service import requirements_for_filing_type

router = APIRouter(prefix="/courts", tags=["Court Rules"])


@router.get(
    "/{court_id}/case-types/{case_type_id}/requirements",
    response_model=list[FilingRequirementResponse],
)
async def get_filing_requirements(
    court_id: int,
    case_type_id: int,
    filing_type: str | None = Query(
        None,
        description=(
            "Scope requirements to a filing context: 'initial' (new case),"
            " 'subsequent'/'motion', or omit for all. Mirrors the submission"
            " validator so the panel shows exactly what will be enforced."
        ),
    ),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FilingRequirement).where(
            FilingRequirement.court_id == court_id,
            FilingRequirement.case_type_id == case_type_id,
        ).order_by(FilingRequirement.is_required.desc())
    )
    requirements = list(result.scalars().all())
    if filing_type:
        requirements = requirements_for_filing_type(requirements, filing_type)
    return requirements


@router.get(
    "/{court_id}/case-types/{case_type_id}/checklist",
    response_model=list[FilingChecklistResponse],
)
async def get_filing_checklist(
    court_id: int,
    case_type_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FilingChecklist).where(
            FilingChecklist.court_id == court_id,
            FilingChecklist.case_type_id == case_type_id,
        )
    )
    return list(result.scalars().all())
