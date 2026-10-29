from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_optional_user_id
from app.api.params import Page, RecordId
from app.database import get_db
from app.models.case import Case, CaseStatus
from app.models.document_public_copy import DocumentPublicCopy
from app.models.filing import PRIVATE_DOCUMENT_TYPES, FilingDocument, FilingEnvelope
from app.models.user import CourtRole, UserCourtRole
from app.schemas.case import (
    CaseDocketResponse,
    CaseSearchResponse,
    CaseSearchResult,
)
from app.schemas.common import MAX_RECORD_ID
from app.schemas.filing import CaseDocumentResponse, CaseFilingResponse
from app.services import access_service, search_service

router = APIRouter(prefix="/cases", tags=["Cases"])


@router.get("/search", response_model=CaseSearchResponse)
async def search_cases(
    case_number: str | None = None,
    party_name: str | None = None,
    attorney_bar_number: str | None = None,
    court_id: int | None = Query(None, ge=1, le=MAX_RECORD_ID),
    case_status: CaseStatus | None = Query(None, alias="status"),
    page: Page = 1,
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Public court-records search — no account required. Sealed matters are excluded
    from the index and the listing strips participant contact PII."""
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
        cases=[CaseSearchResult.model_validate(c) for c in cases],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{case_id}", response_model=CaseDocketResponse)
async def get_case(
    case_id: RecordId,
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int | None = Depends(get_optional_user_id),
):
    """Public docket for a single case. Non-sealed: open to anyone; sealed: restricted."""
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
    profile = CaseDocketResponse.model_validate(case)
    return profile.model_copy(update={
        "can_manage_records": await access_service.user_is_court_staff_for_court(
            db, user_id, case.court_id,
        ),
        "can_file": user_id is not None and await access_service.user_may_file_on_case(
            db, user_id, case_id,
        ),
    })


@router.get("/{case_id}/filings", response_model=list[CaseFilingResponse])
async def get_case_filings(
    case_id: RecordId,
    page: Page = 1,
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db, scope="function"),
    user_id: int | None = Depends(get_optional_user_id),
):
    case = await db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if not await access_service.user_may_read_case(db, user_id, case_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access filings for this case",
        )
    # Newest first by the court's filing date; filings without one (still in review)
    # sort by submission. A draft's creation time says nothing about docket order.
    query = (
        select(FilingEnvelope)
        .where(FilingEnvelope.case_id == case_id)
        .order_by(
            func.coalesce(
                FilingEnvelope.filing_date, FilingEnvelope.submitted_at,
                FilingEnvelope.created_at,
            ).desc(),
            FilingEnvelope.id.desc(),
        )
    )
    # Standing on a case does not expose another filer's drafts or waiver request.
    staff_courts = select(UserCourtRole.court_id).where(
        UserCourtRole.user_id == user_id,
        UserCourtRole.role.in_([CourtRole.CLERK, CourtRole.JUDGE, CourtRole.ADMIN]),
    )
    visible: ColumnElement[bool] = FilingEnvelope.status.in_(
        access_service.PUBLIC_DOCKET_FILING_STATUSES
    )
    if user_id is not None:
        visible = or_(visible, FilingEnvelope.filer_id == user_id,
                      FilingEnvelope.court_id.in_(staff_courts))
    query = query.where(visible)
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    staff = await access_service.user_is_court_staff_for_court(db, user_id, case.court_id)
    filings = list(result.scalars())
    # Court orders belong on the docket, but never in the filer's attachment manifest.
    # Load all current docket documents once, including separately recorded date orders.
    documents: dict[int, list[FilingDocument]] = {}
    if filings:
        for doc in await db.scalars(select(FilingDocument).where(
            FilingDocument.envelope_id.in_([filing.id for filing in filings]),
            FilingDocument.removed_at.is_(None),
            FilingDocument.document_type_code != "FEE_WAIVER_ORDER",
        ).order_by(FilingDocument.id)):
            documents.setdefault(doc.envelope_id, []).append(doc)
    copy_ids = {
        doc.public_copy_id for filing in filings for doc in documents.get(filing.id, [])
        if doc.public_copy_id and not staff and filing.filer_id != user_id
    }
    copies = {copy.id: copy for copy in await db.scalars(
        select(DocumentPublicCopy).where(DocumentPublicCopy.id.in_(copy_ids))
    )} if copy_ids else {}
    entries = []
    for filing in filings:
        visible_documents = []
        for doc in documents.get(filing.id, []):
            if not staff and filing.filer_id != user_id:
                if doc.document_type_code in PRIVATE_DOCUMENT_TYPES:
                    continue
                copy = copies.get(doc.public_copy_id) if doc.public_copy_id else None
                if copy and copy.document_id == doc.id:
                    # Never copy the original title, hash, size or private flags into
                    # the public derivative's response. Only its reviewed metadata is public.
                    visible_documents.append(CaseDocumentResponse(
                        id=doc.id, copy_id=copy.id, document_type_code="PUBLIC_COPY",
                        title=copy.title,
                        file_size_bytes=copy.file_size_bytes, mime_type=copy.mime_type,
                        page_count=copy.page_count, sha256_hash=copy.sha256_hash,
                        is_confidential=False, is_text_searchable=copy.is_text_searchable,
                        uploaded_at=copy.created_at,
                    ))
                elif not doc.is_confidential:
                    visible_documents.append(CaseDocumentResponse.model_validate(doc))
            else:
                visible_documents.append(CaseDocumentResponse.model_validate(doc))
        entries.append(CaseFilingResponse(
            id=filing.id, status=filing.status, case_title=filing.case_title,
            filing_description=filing.filing_description, submitted_at=filing.submitted_at,
            reviewed_at=filing.reviewed_at, rejection_reason=filing.rejection_reason,
            documents=visible_documents, created_at=filing.created_at,
            filing_date=filing.filing_date,
        ))
    return entries
