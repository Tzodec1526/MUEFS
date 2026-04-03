from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.case import Case, CaseParticipant, CaseStatus
from app.models.court import FilingRequirement
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.schemas.filing import (
    FilingEnvelopeCreate,
    FilingValidationResult,
)


async def create_filing(
    db: AsyncSession,
    filer_id: int,
    data: FilingEnvelopeCreate,
) -> FilingEnvelope:
    envelope = FilingEnvelope(
        court_id=data.court_id,
        case_id=data.case_id,
        case_type_id=data.case_type_id,
        filer_id=filer_id,
        filing_type=data.filing_type,
        case_title=data.case_title,
        filing_description=data.filing_description,
        status=FilingStatus.DRAFT,
    )
    db.add(envelope)
    await db.flush()
    return envelope


async def get_filing(db: AsyncSession, filing_id: int) -> FilingEnvelope | None:
    result = await db.execute(
        select(FilingEnvelope)
        .options(selectinload(FilingEnvelope.documents))
        .where(FilingEnvelope.id == filing_id)
    )
    return result.scalar_one_or_none()


async def list_filings(
    db: AsyncSession,
    filer_id: int,
    status: FilingStatus | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[FilingEnvelope], int]:
    query = (
        select(FilingEnvelope)
        .options(selectinload(FilingEnvelope.documents))
        .where(FilingEnvelope.filer_id == filer_id)
        .order_by(FilingEnvelope.updated_at.desc())
    )
    count_query = select(func.count()).select_from(FilingEnvelope).where(
        FilingEnvelope.filer_id == filer_id
    )

    if status:
        query = query.where(FilingEnvelope.status == status)
        count_query = count_query.where(FilingEnvelope.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def validate_filing(
    db: AsyncSession,
    filing_id: int,
) -> FilingValidationResult:
    filing = await get_filing(db, filing_id)
    if not filing:
        return FilingValidationResult(
            is_valid=False, errors=["Filing not found"]
        )

    errors: list[str] = []
    warnings: list[str] = []
    missing_docs: list[str] = []

    if not filing.documents:
        errors.append("At least one document must be uploaded")

    # Service-only filings have relaxed validation - just need docs and a case
    is_service_only = filing.filing_type == "service_only"

    if is_service_only:
        if not filing.case_id:
            errors.append("Service-only filings must reference an existing case")
    else:
        # Check required documents against court rules
        requirements = await db.execute(
            select(FilingRequirement).where(
                FilingRequirement.court_id == filing.court_id,
                FilingRequirement.case_type_id == filing.case_type_id,
                FilingRequirement.is_required == True,  # noqa: E712
            )
        )
        required_docs = list(requirements.scalars().all())

        filed_doc_types = {doc.document_type_code for doc in filing.documents}
        for req in required_docs:
            if req.document_type_code not in filed_doc_types:
                missing_docs.append(
                    f"{req.description} ({req.document_type_code})"
                    + (f" - See {req.mcr_reference}" if req.mcr_reference else "")
                )

        if not filing.case_title and not filing.case_id:
            errors.append("Case title is required for new case filings")

    # Check document sizes and types
    for doc in filing.documents:
        if not doc.is_text_searchable and doc.mime_type == "application/pdf":
            warnings.append(
                f"Document '{doc.title}' may not be text-searchable. "
                "MCR 1.109 requires text-searchable PDFs."
            )

    is_valid = len(errors) == 0 and len(missing_docs) == 0
    return FilingValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
        missing_required_documents=missing_docs,
    )


async def submit_filing(
    db: AsyncSession,
    filing_id: int,
) -> FilingEnvelope | None:
    filing = await get_filing(db, filing_id)
    if not filing or filing.status != FilingStatus.DRAFT:
        return None

    now = datetime.now(timezone.utc)
    filing.submitted_at = now

    # Service-only filings skip clerk review entirely
    if filing.filing_type == "service_only":
        filing.status = FilingStatus.SERVED
        filing.reviewed_at = now
    else:
        filing.status = FilingStatus.SUBMITTED

    await db.flush()
    await db.refresh(filing)
    return filing


async def review_filing(
    db: AsyncSession,
    filing_id: int,
    reviewer_id: int,
    action: str,
    reason: str | None = None,
) -> FilingEnvelope | None:
    filing = await get_filing(db, filing_id)
    if not filing or filing.status not in (FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW):
        return None

    now = datetime.now(timezone.utc)
    filing.reviewer_id = reviewer_id
    filing.reviewed_at = now

    if action == "accept":
        filing.status = FilingStatus.ACCEPTED
        # Create case if this is a new filing (no existing case_id)
        if not filing.case_id:
            case = Case(
                court_id=filing.court_id,
                case_number=f"MI-{filing.court_id}-{now.strftime('%Y')}-{filing.id:06d}",
                case_type_id=filing.case_type_id,
                title=filing.case_title or "Untitled Case",
                status=CaseStatus.OPEN,
                filed_date=now,
            )
            db.add(case)
            await db.flush()
            filing.case_id = case.id
    elif action == "reject":
        filing.status = FilingStatus.REJECTED
        filing.rejection_reason = reason
    elif action == "return":
        filing.status = FilingStatus.RETURNED
        filing.rejection_reason = reason
    else:
        return None

    await db.flush()
    return filing


async def get_clerk_queue(
    db: AsyncSession,
    court_id: int,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[FilingEnvelope], int]:
    query = (
        select(FilingEnvelope)
        .options(selectinload(FilingEnvelope.documents))
        .where(
            FilingEnvelope.court_id == court_id,
            FilingEnvelope.status.in_([FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW]),
        )
        .order_by(FilingEnvelope.submitted_at.asc())
    )
    count_query = (
        select(func.count())
        .select_from(FilingEnvelope)
        .where(
            FilingEnvelope.court_id == court_id,
            FilingEnvelope.status.in_([FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW]),
        )
    )

    total = (await db.execute(count_query)).scalar() or 0
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all()), total
