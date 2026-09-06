from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_optional_user_id
from app.database import get_db
from app.models.case import Case, CaseStatus
from app.models.document_public_copy import DocumentPublicCopy
from app.models.filing import PRIVATE_DOCUMENT_TYPES, FilingEnvelope
from app.models.user import CourtRole, UserCourtRole
from app.schemas.case import (
    CaseDocketResponse,
    CaseSearchResponse,
)
from app.schemas.filing import CaseDocumentResponse, CaseFilingResponse
from app.services import access_service, search_service

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
    _user_id: int | None = Depends(get_optional_user_id),
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
        cases=[CaseDocketResponse.model_validate(c) for c in cases],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{case_id}", response_model=CaseDocketResponse)
async def get_case(
    case_id: int,
    db: AsyncSession = Depends(get_db),
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
    return profile.model_copy(update={"can_manage_records":
        await access_service.user_is_court_staff_for_court(db, user_id, case.court_id)})


@router.get("/{case_id}/filings", response_model=list[CaseFilingResponse])
async def get_case_filings(
    case_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user_id: int | None = Depends(get_optional_user_id),
):
    if not await access_service.user_may_read_case(db, user_id, case_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access filings for this case",
        )
    case = await db.get(Case, case_id)
    query = (
        select(FilingEnvelope)
        .options(selectinload(FilingEnvelope.documents))
        .where(FilingEnvelope.case_id == case_id)
        .order_by(FilingEnvelope.created_at.desc(), FilingEnvelope.id.desc())
    )
    # Standing on a case does not expose another filer's drafts or waiver request.
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
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
    copy_ids = {
        doc.public_copy_id for filing in filings for doc in filing.documents
        if doc.public_copy_id and not staff and filing.filer_id != user_id
    }
    copies = {copy.id: copy for copy in await db.scalars(
        select(DocumentPublicCopy).where(DocumentPublicCopy.id.in_(copy_ids))
    )} if copy_ids else {}
    entries = []
    for filing in filings:
        entry = CaseFilingResponse.model_validate(filing)
        if not staff and filing.filer_id != user_id:
            visible_documents = []
            for doc, response in zip(filing.documents, entry.documents, strict=True):
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
                    visible_documents.append(response)
            entry.documents = visible_documents
        entries.append(entry)
    return entries
