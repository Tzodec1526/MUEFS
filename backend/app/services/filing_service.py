from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.integrations.cms_adapter import submit_filing_to_cms
from app.models.case import Case, CaseStatus
from app.models.court import FilingRequirement
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.schemas.filing import (
    FilingEnvelopeCreate,
    FilingValidationResult,
)
from app.services import access_service, document_service
from app.services.court_calendar_service import filing_date_for_receipt
from app.services.filing_record_service import record_transaction


class FilingCreateError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class CmsSubmissionError(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class FilingDateUnavailableError(Exception):
    pass


class FilingDocumentError(Exception):
    pass


async def verify_filing_documents(
    filing: FilingEnvelope, court_order: FilingDocument | None = None,
) -> None:
    """Confirm current attachment bytes before creating a receipt or accepting a filing."""
    from botocore.exceptions import BotoCoreError, ClientError

    if not filing.documents:
        raise FilingDocumentError("The filing has no current documents to verify")
    documents = [*filing.documents, court_order] if court_order else filing.documents
    for doc in documents:
        try:
            digest, size = await run_in_threadpool(document_service.stored_integrity, doc.file_key)
        except (OSError, BotoCoreError, ClientError) as exc:
            raise FilingDocumentError(
                f"Stored document '{doc.title}' is unavailable. "
                "Retry when storage is available, or contact the court to restore the file."
            ) from exc
        if digest != doc.sha256_hash or size != doc.file_size_bytes:
            raise FilingDocumentError(
                f"Stored document '{doc.title}' does not match its recorded fingerprint or size. "
                "Replace the draft attachment or contact the court to restore the original."
            )

# Document-code classifiers shared by the submission validator and the
# requirements API, so the UI shows exactly the set the validator enforces.
_SERVICE_PROOF_CODES = {"PROOF_SERVICE", "POS_ELECTRONIC", "CERT_SERVICE"}

# MCR 2.313(A): the good-faith (meet-and-confer) certification accompanies discovery
# motions only; other motions do not need it.
_DISCOVERY_MOTION_CODES = {"MOT_COMPEL", "MOT_PROTECTIVE", "MOT_SANCTIONS"}


def _is_motion_code(code: str) -> bool:
    c = code.upper()
    return (
        c.startswith("MOT_")
        or c in (
            # NOTICE_HEARING is the probate lists' spelling; the catalog uses NOT_HEARING.
            "MOTION", "BRIEF", "BRIEF_SUPPORT", "BRIEF_RESPONSE", "BRIEF_REPLY",
            "PROPOSED_ORDER", "NOT_HEARING", "NOTICE_HEARING", "DISC_CERT_GF",
        )
        or "MOTION" in c
        or "BRIEF" in c
    )


def _is_response_code(code: str) -> bool:
    c = code.upper()
    return (
        c in ("ANSWER", "REPLY", "RESPONSE_BRIEF", "BRIEF_RESPONSE", "BRIEF_REPLY")
        or "ANSWER" in c
        or "REPLY" in c
    )


def requirements_for_filing_type(
    requirements: list[FilingRequirement],
    filing_type: str,
) -> list[FilingRequirement]:
    """Return the subset of court-rule requirements that apply to a filing context.

    Mirrors the enforcement logic in :func:`validate_filing` so the requirements
    panel can display exactly what the validator will enforce.

    - ``initial`` (new case): initiating pleadings only. Motion companions,
      responsive documents, and proof/certificate of service are dropped --
      service (and its proof) happens *after* the case is filed and the summons
      issued (MCR 2.104 / 2.107).
    - ``subsequent`` / ``motion``: motion-related companions only; the original
      complaint and similar initiating documents are already on file.
    - any other type (e.g. service-only): returned unfiltered.
    """
    if filing_type == "initial":
        return [
            r
            for r in requirements
            if not (
                _is_motion_code(r.document_type_code)
                or _is_response_code(r.document_type_code)
                or r.document_type_code.upper() in _SERVICE_PROOF_CODES
            )
        ]
    if filing_type in ("subsequent", "motion"):
        return [r for r in requirements if _is_motion_code(r.document_type_code)]
    return list(requirements)


async def create_filing(
    db: AsyncSession,
    filer_id: int,
    data: FilingEnvelopeCreate,
) -> FilingEnvelope:
    if data.case_id is not None:
        case_row = await db.execute(select(Case).where(Case.id == data.case_id))
        case = case_row.scalar_one_or_none()
        if case is None:
            raise FilingCreateError(404, "Case not found")
        if case.court_id != data.court_id:
            raise FilingCreateError(400, "Case does not belong to the selected court")
        if not await access_service.user_may_read_case(db, filer_id, case.id):
            raise FilingCreateError(403, "Not authorized to file on this case")

    envelope = FilingEnvelope(
        court_id=data.court_id,
        case_id=data.case_id,
        case_type_id=data.case_type_id,
        filer_id=filer_id,
        filing_type=data.filing_type,
        case_title=data.case_title,
        filing_description=data.filing_description,
        fee_waiver_requested=data.fee_waiver_requested,
        fee_waiver_reason=data.fee_waiver_reason,
        status=FilingStatus.DRAFT,
    )
    db.add(envelope)
    await db.flush()
    await db.refresh(envelope)
    await db.refresh(envelope, ["documents"])
    return envelope


async def get_filing(
    db: AsyncSession, filing_id: int, *, for_update: bool = False,
) -> FilingEnvelope | None:
    query = (
        select(FilingEnvelope)
        .options(selectinload(FilingEnvelope.documents))
        .where(FilingEnvelope.id == filing_id)
    )
    if for_update:
        # A request may already have read the row for authorization. Refresh that
        # identity-map entry after the lock, or concurrent decisions can use stale status.
        query = query.with_for_update().execution_options(populate_existing=True)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_filings(
    db: AsyncSession,
    filer_id: int,
    status: FilingStatus | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[FilingEnvelope], int, dict[FilingStatus, int]]:
    query = (
        select(FilingEnvelope)
        .options(selectinload(FilingEnvelope.documents))
        .where(FilingEnvelope.filer_id == filer_id)
        .order_by(FilingEnvelope.updated_at.desc(), FilingEnvelope.id.desc())
    )
    status_counts = await get_filing_status_counts(db, filer_id)

    if status:
        query = query.where(FilingEnvelope.status == status)

    total = status_counts[status] if status else sum(status_counts.values())
    if not total:
        return [], 0, status_counts
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all()), total, status_counts


async def get_filing_status_counts(db: AsyncSession, filer_id: int) -> dict[FilingStatus, int]:
    result = await db.execute(
        select(FilingEnvelope.status, func.count())
        .where(FilingEnvelope.filer_id == filer_id)
        .group_by(FilingEnvelope.status)
    )
    return dict.fromkeys(FilingStatus, 0) | dict(result.tuples().all())


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
    if filing.fee_waiver_requested and filing.fee_waiver_granted is None and not any(
        doc.document_type_code == "FEE_WAIVER" for doc in filing.documents
    ):
        missing_docs.append("Completed, signed Fee Waiver Request (MC 20) — nonpublic")

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

        required_docs = requirements_for_filing_type(required_docs, filing.filing_type)

        for req in required_docs:
            code = req.document_type_code
            satisfied = code in filed_doc_types
            if not satisfied and (code.startswith("MOT_") or code == "MOTION"):
                # Any motion document satisfies a motion-document requirement, in both
                # directions: a specific type (MOT_SD, MOT_RECONSIDER, ...) covers a
                # generic MOTION row and vice versa.
                satisfied = any(dt.startswith("MOT_") or dt == "MOTION" for dt in filed_doc_types)
            if (
                not satisfied
                and code == "DISC_CERT_GF"
                and not (filed_doc_types & _DISCOVERY_MOTION_CODES)
            ):
                # The certification requirement applies only to discovery motions.
                satisfied = True
            if not satisfied:
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

    # Advisory screening is tied to the uploaded bytes. Transitions independently
    # verify those bytes; repeating PDF extraction here adds no new assurance.
    for doc in filing.documents:
        if doc.mime_type == "application/pdf":
            if doc.pii_warnings is None:
                warnings.append(
                    f"Document '{doc.title}' has no retained PII screening result. "
                    "Review its full contents before submission."
                )
            else:
                warnings.extend(f"Document '{doc.title}': {w}" for w in doc.pii_warnings)

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
    *, idempotency_key: str | None = None,
) -> FilingEnvelope | None:
    filing = await get_filing(db, filing_id, for_update=True)
    if not filing or filing.status not in (FilingStatus.DRAFT, FilingStatus.RETURNED):
        return None

    await verify_filing_documents(filing)
    now = datetime.now(UTC)
    filing.submitted_at = now
    filing.reviewed_at = None
    filing.reviewer_id = None
    filing.rejection_reason = None
    filing.cms_error = None
    filing.submission_count += 1
    filing.filing_date_version += 1
    if filing.filing_type != "service_only":
        assessment = await filing_date_for_receipt(db, filing.court_id, now)
        filing.filing_date = assessment.filing_date
        filing.filing_date_basis = assessment.model_dump(mode="json")

    # Service-only filings skip clerk review entirely
    if filing.filing_type == "service_only":
        filing.status = FilingStatus.SERVED
        filing.reviewed_at = now
    else:
        filing.status = FilingStatus.SUBMITTED

    await record_transaction(
        db, filing, "service_recorded" if filing.filing_type == "service_only" else "submitted",
        filing.filer_id, idempotency_key=idempotency_key,
    )
    await db.flush()
    await db.refresh(filing)
    await db.refresh(filing, ["documents"])
    return filing


async def _case_for_accept(db: AsyncSession, filing: FilingEnvelope, now: datetime) -> Case:
    if filing.case_id:
        case_row = await db.execute(select(Case).where(Case.id == filing.case_id))
        case = case_row.scalar_one_or_none()
        if case is None:
            raise CmsSubmissionError("Accepted filing references a missing case")
        return case
    case = Case(
        court_id=filing.court_id,
        case_number=f"MI-{filing.court_id}-{now.strftime('%Y')}-{filing.id:06d}",
        case_type_id=filing.case_type_id,
        title=filing.case_title or "Untitled Case",
        status=CaseStatus.OPEN,
        filed_date=filing.submitted_at,
        filing_date=filing.filing_date,
    )
    return case


async def review_filing(
    db: AsyncSession,
    filing_id: int,
    reviewer_id: int,
    action: str,
    reason: str | None = None,
) -> FilingEnvelope | None:
    filing = await get_filing(db, filing_id, for_update=True)
    if not filing or filing.status not in (FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW):
        return None

    ordered_date = (filing.filing_date_basis or {}).get("source") == "court_order"
    if action == "accept":
        court_order = None
        if ordered_date:
            basis = filing.filing_date_basis or {}
            court_order = await db.scalar(select(FilingDocument).where(
                FilingDocument.id == basis.get("order_document_id"),
                FilingDocument.envelope_id == filing.id,
                FilingDocument.document_type_code == "FILING_DATE_ORDER",
                FilingDocument.retained_at.is_not(None),
            ))
            if (court_order is None or filing.filing_date is None
                    or basis.get("submission_number") != filing.submission_count):
                raise FilingDateUnavailableError("The filing-date order requires court review")
        await verify_filing_documents(filing, court_order)
    now = datetime.now(UTC)
    filing.reviewer_id = reviewer_id
    filing.reviewed_at = now

    if action == "accept":
        if filing.submitted_at is None:
            raise FilingDateUnavailableError("The filing has no recorded receipt time")
        if not ordered_date:
            assessment = await filing_date_for_receipt(db, filing.court_id, filing.submitted_at)
            if assessment.filing_date is None and not settings.allow_demo_mode:
                raise FilingDateUnavailableError(
                    assessment.error or "The court filing date is unresolved"
                )
            basis = assessment.model_dump(mode="json")
            if filing.filing_date_basis != basis:
                previous_date = filing.filing_date.isoformat() if filing.filing_date else None
                filing.filing_date = assessment.filing_date
                filing.filing_date_basis = basis
                await record_transaction(db, filing, "filing_date_assessed", reviewer_id, details={
                    "previous_filing_date": previous_date, "filing_date_basis": basis,
                })
        # Acceptance can create the case. An already-open date form must be refreshed.
        filing.filing_date_version += 1
        filing.status = FilingStatus.UNDER_REVIEW
        case = await _case_for_accept(db, filing, now)
        cms_result = await submit_filing_to_cms(case.case_number, filing.id)
        if not cms_result.success:
            filing.cms_error = cms_result.error_message or "CMS submission failed"
            filing.cms_filing_id = None
            filing.cms_case_number = None
            await record_transaction(db, filing, "cms_failed", reviewer_id, reason=filing.cms_error)
            await db.flush()
            await db.refresh(filing)
            await db.refresh(filing, ["documents"])
            return filing
        if filing.case_id is None:
            db.add(case)
            await db.flush()
            filing.case_id = case.id
        filing.status = FilingStatus.ACCEPTED
        filing.cms_filing_id = cms_result.cms_filing_id
        filing.cms_case_number = cms_result.cms_case_number
        filing.cms_error = None
    elif action == "reject":
        filing.filing_date_version += 1
        filing.status = FilingStatus.REJECTED
        filing.rejection_reason = reason
    elif action == "return":
        filing.filing_date_version += 1
        filing.status = FilingStatus.RETURNED
        filing.rejection_reason = reason
    else:
        return None

    await record_transaction(db, filing, filing.status.value, reviewer_id, reason=reason)
    await db.flush()
    await db.refresh(filing)
    await db.refresh(filing, ["documents"])
    return filing


async def get_clerk_queue(
    db: AsyncSession,
    court_id: int,
    page: int = 1,
    page_size: int = 25,
    status: FilingStatus | None = None,
    fee_waivers: bool = False,
) -> tuple[list[FilingEnvelope], int]:
    filters = [
        FilingEnvelope.court_id == court_id,
        FilingEnvelope.status.in_([FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW]),
    ]
    if fee_waivers:
        filters = [
            FilingEnvelope.court_id == court_id,
            FilingEnvelope.fee_waiver_requested.is_(True),
            FilingEnvelope.fee_waiver_granted.is_(None),
            FilingEnvelope.submitted_at.is_not(None),
            FilingEnvelope.status.not_in([FilingStatus.REJECTED, FilingStatus.SERVED]),
        ]
    if status is not None:
        filters.append(FilingEnvelope.status == status)
    query = (
        select(FilingEnvelope)
        .options(selectinload(FilingEnvelope.documents))
        .where(*filters)
        .order_by(FilingEnvelope.submitted_at.asc(), FilingEnvelope.id.asc())
    )
    count_query = (
        select(func.count())
        .select_from(FilingEnvelope)
        .where(*filters)
    )

    total = (await db.execute(count_query)).scalar() or 0
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all()), total
