"""Public, unauthenticated endpoints for demo transparency and landing stats."""

from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.case import Case
from app.models.court import Court, FilingRequirement
from app.models.filing import FilingEnvelope, FilingStatus

router = APIRouter(prefix="/public", tags=["Public"])


@router.get("/stats")
async def get_public_platform_stats(db: AsyncSession = Depends(get_db)):
    """Aggregate counts for the demo landing — no auth, no PII."""
    total_courts = (
        await db.execute(
            select(func.count()).select_from(Court).where(Court.is_efiling_enabled.is_(True))
        )
    ).scalar() or 0
    public_cases = (
        await db.execute(
            select(func.count()).select_from(Case).where(Case.is_sealed.is_(False))
        )
    ).scalar() or 0
    total_filings = (
        await db.execute(select(func.count()).select_from(FilingEnvelope))
    ).scalar() or 0
    pending_review = (
        await db.execute(
            select(func.count())
            .select_from(FilingEnvelope)
            .where(
                FilingEnvelope.status.in_(
                    [FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW]
                )
            )
        )
    ).scalar() or 0
    document_types = (
        await db.execute(select(func.count(distinct(FilingRequirement.document_type_code))))
    ).scalar() or 0

    return {
        "courts_efiling_enabled": total_courts,
        "public_cases_indexed": public_cases,
        "total_filings": total_filings,
        "pending_clerk_review": pending_review,
        "mcr_document_types": document_types,
        "max_upload_mb": 100,
        "mifile_max_upload_mb": 25,
        "cms_integration": "stub",
    }
