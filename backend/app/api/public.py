from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.case import Case
from app.models.court import Court, FilingRequirement
from app.models.filing import FilingEnvelope, FilingStatus

router = APIRouter(prefix="/public", tags=["Public"])


@router.get("/stats")
async def get_public_platform_stats(db: AsyncSession = Depends(get_db, scope="function")):
    counts = (await db.execute(select(
        select(func.count()).select_from(Court).where(Court.is_efiling_enabled.is_(True))
        .scalar_subquery(),
        select(func.count()).select_from(Case).where(Case.is_sealed.is_(False))
        .scalar_subquery(),
        select(func.count()).select_from(FilingEnvelope).scalar_subquery(),
        select(func.count())
        .select_from(FilingEnvelope)
        .where(
            FilingEnvelope.status.in_(
                [FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW]
            )
        )
        .scalar_subquery(),
        select(func.count(distinct(FilingRequirement.document_type_code))).scalar_subquery(),
    ))).one()
    total_courts, public_cases, total_filings, pending_review, document_types = (
        count or 0 for count in counts
    )

    return {
        "courts_efiling_enabled": total_courts,
        "public_cases_indexed": public_cases,
        "total_filings": total_filings,
        "pending_clerk_review": pending_review,
        "mcr_document_types": document_types,
        "max_upload_mb": settings.max_file_size_mb,
        "mifile_max_upload_mb": 25,
        "cms_integration": "stub",
    }
