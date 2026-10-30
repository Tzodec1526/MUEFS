import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.case_numbers import case_number_code
from app.config import settings
from app.integrations.cms_adapter import submit_filing_to_cms
from app.models.case import Case, CaseStatus
from app.models.court import CaseType, Court, FilingRequirement
from app.models.filing import COURT_DOCUMENT_TYPES, FilingDocument, FilingEnvelope, FilingStatus
from app.models.filing_transaction import FilingTransaction
from app.models.user import User
from app.schemas.common import MAX_RECORD_ID
from app.schemas.filing import (
    ClerkQueueResponse,
    FilingEnvelopeCreate,
    FilingEnvelopeUpdate,
    FilingSummary,
    FilingValidationResult,
)
from app.services import access_service, document_service
from app.services.court_calendar_service import filing_date_for_receipt
from app.services.fee_assessment_service import fee_state
from app.services.filing_record_service import record_transaction


class FilingDestinationError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class FilingDateUnavailableError(Exception):
    pass


class FilingDocumentError(Exception):
    pass


class StaleFilingReviewError(Exception):
    pass


class FilingSubmissionError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class FilingUpdateError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class SubmissionAlreadyRecordedError(Exception):
    def __init__(self, filing: FilingEnvelope):
        self.filing = filing
        super().__init__(f"Filing {filing.id} already recorded this submission request")


async def verify_filing_documents(
    filing: FilingEnvelope, court_order: FilingDocument | None = None,
) -> None:
    """Confirm current attachment bytes before creating a receipt or accepting a filing."""
    if not filing.documents:
        raise FilingDocumentError("The filing has no current documents to verify")
    documents = [*filing.documents, court_order] if court_order else filing.documents
    for doc in documents:
        try:
            digest, size = await run_in_threadpool(document_service.stored_integrity, doc.file_key)
        except OSError as exc:  # Missing, or storage unavailable
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
      complaint and similar initiating documents are already on file. The validator
      enforces them on a subsequent filing only when it includes a motion.
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


async def validate_filing_destination(
    db: AsyncSession, data: FilingEnvelopeCreate | FilingEnvelope, *, filer_id: int | None,
    lock: bool = True,
) -> Case | None:
    """Court review checks routing; intake also checks availability and filer access."""
    if data.filing_type not in ("initial", "subsequent", "motion", "service_only"):
        raise FilingDestinationError(
            409, "This record has an unsupported filing type and needs correction.",
        )
    if filer_id is None and data.filing_type == "service_only":
        raise FilingDestinationError(
            409, "A service-only record cannot be accepted as a court filing",
        )
    if filer_id is not None and (data.filing_type == "initial") != (data.case_id is None):
        raise FilingDestinationError(
            409, "The filing type does not match its case reference. Start a new draft.",
        )
    # Read current scalar values, even if a caller previously loaded these records.
    # Shared locks keep configuration and case access stable until the receipt commits.
    target_query = (
        select(Court.is_efiling_enabled, Court.intake_notice, CaseType.court_id, CaseType.is_active)
        .select_from(Court).join(CaseType, CaseType.id == data.case_type_id)
        .where(Court.id == data.court_id)
    )
    if lock:
        target_query = target_query.with_for_update(read=True, of=(Court, CaseType))
    target = (await db.execute(target_query)).one_or_none()
    if target is None:
        raise FilingDestinationError(404, "The selected court or case type was not found")
    if target.court_id != data.court_id:
        raise FilingDestinationError(400, "Case type does not belong to the selected court")
    if filer_id is not None and not target.is_efiling_enabled:
        raise FilingDestinationError(
            409, "This court is not accepting electronic filings. "
            + (target.intake_notice or "Contact the court for filing options."),
        )
    if filer_id is not None and not target.is_active:
        raise FilingDestinationError(
            409, "This case type is not accepting electronic filings. "
            + (target.intake_notice or "Contact the court for guidance."),
        )
    case = None
    if data.case_id is not None:
        case_query = (
            select(Case).where(Case.id == data.case_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            case_query = case_query.with_for_update(read=True)
        case = await db.scalar(case_query)
        if case is None:
            raise FilingDestinationError(404, "Case not found")
        filer = await db.get(User, filer_id) if filer_id is not None else None
        if filer_id is not None and (
            filer is None
            or not await access_service.user_may_file_on_case(db, filer, data.case_id)
        ):
            raise FilingDestinationError(
                403, "Court-reviewed case participation is required to file on this case",
            )
        if case.court_id != data.court_id:
            raise FilingDestinationError(400, "Case does not belong to the selected court")
        if case.case_type_id != data.case_type_id:
            raise FilingDestinationError(400, "Case type does not match the selected case")
    return case


def creation_fingerprint(data: FilingEnvelopeCreate) -> str:
    # Include validated defaults so omitted fields and their explicit defaults replay alike.
    return hashlib.sha256(json.dumps(
        data.model_dump(mode="json"), sort_keys=True, ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


async def create_filing(
    db: AsyncSession,
    filer_id: int,
    data: FilingEnvelopeCreate,
    *,
    creation_key: str | None = None,
) -> FilingEnvelope:
    case = await validate_filing_destination(db, data, filer_id=filer_id)

    envelope = FilingEnvelope(
        court_id=data.court_id,
        case_id=data.case_id,
        case_type_id=data.case_type_id,
        filer_id=filer_id,
        creation_key=creation_key,
        creation_sha256=creation_fingerprint(data) if creation_key else None,
        filing_type=data.filing_type,
        # A filing into an existing case carries the court's caption, not a client value.
        case_title=case.title if case is not None else data.case_title,
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


async def update_details(
    db: AsyncSession, filing: FilingEnvelope, data: FilingEnvelopeUpdate,
) -> FilingEnvelope:
    if (
        data.expected_details_token is not None
        and data.expected_details_token != filing.details_token
    ):
        raise FilingUpdateError(
            409,
            "This filing changed after you opened it. Compare the saved details "
            "with your edits before saving again.",
        )
    if filing.status not in (FilingStatus.DRAFT, FilingStatus.RETURNED):
        raise FilingUpdateError(400, "Can only update draft or returned filings")

    if filing.submitted_at is not None and (
        (data.fee_waiver_requested is not None
         and data.fee_waiver_requested != filing.fee_waiver_requested)
        or (data.fee_waiver_reason is not None
            and data.fee_waiver_reason != filing.fee_waiver_reason)
    ):
        raise FilingUpdateError(
            409, "A submitted fee waiver request cannot be changed through draft editing",
        )

    if data.case_title is not None and data.case_title != filing.case_title:
        if filing.case_id is not None:
            raise FilingUpdateError(
                409, "A filing in an existing case uses the court's case title.",
            )
        filing.case_title = data.case_title
    if data.filing_description is not None:
        filing.filing_description = data.filing_description
    if data.fee_waiver_requested is not None:
        filing.fee_waiver_requested = data.fee_waiver_requested
        if data.fee_waiver_requested:
            filing.fee_review_requested_at = None
    if data.fee_waiver_reason is not None:
        filing.fee_waiver_reason = data.fee_waiver_reason

    await db.flush()
    await db.refresh(filing)
    await db.refresh(filing, ["documents"])
    return filing


async def get_filing(
    db: AsyncSession, filing_id: int, *, for_update: bool = False,
) -> FilingEnvelope | None:
    query = (
        select(FilingEnvelope)
        .options(selectinload(FilingEnvelope.documents))
        .where(FilingEnvelope.id == filing_id)
        .execution_options(populate_existing=True)
    )
    if for_update:
        # A request may already have read the row for authorization. Refresh that
        # identity-map entry after the lock, or concurrent decisions can use stale status.
        query = query.with_for_update()
    result = await db.execute(query)
    return result.scalar_one_or_none()


_FILING_SUMMARIES = select(
    FilingEnvelope.id,
    FilingEnvelope.court_id,
    FilingEnvelope.case_id,
    FilingEnvelope.filer_id,
    FilingEnvelope.status,
    FilingEnvelope.case_title,
    FilingEnvelope.filing_description,
    FilingEnvelope.submitted_at,
    FilingEnvelope.rejection_reason,
    FilingEnvelope.fee_waiver_requested,
    FilingEnvelope.fee_waiver_granted,
    FilingEnvelope.created_at,
    FilingEnvelope.updated_at,
    FilingEnvelope.submission_count,
    # Count current attachments using the same scope as FilingEnvelope.documents.
    select(func.count())
    .select_from(FilingDocument)
    .where(
        FilingDocument.envelope_id == FilingEnvelope.id,
        FilingDocument.removed_at.is_(None),
        FilingDocument.document_type_code.not_in(COURT_DOCUMENT_TYPES),
    )
    .correlate(FilingEnvelope)
    .scalar_subquery()
    .label("document_count"),
)


async def list_filings(
    db: AsyncSession,
    filer_id: int,
    status: FilingStatus | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[FilingSummary], int, dict[FilingStatus, int]]:
    query = (
        _FILING_SUMMARIES
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
    return [FilingSummary.model_validate(row) for row in result], total, status_counts


async def get_filing_status_counts(db: AsyncSession, filer_id: int) -> dict[FilingStatus, int]:
    result = await db.execute(
        select(FilingEnvelope.status, func.count())
        .where(FilingEnvelope.filer_id == filer_id)
        .group_by(FilingEnvelope.status)
    )
    return dict.fromkeys(FilingStatus, 0) | dict(result.tuples().all())


async def validate_filing(
    db: AsyncSession,
    filing: FilingEnvelope,
) -> FilingValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    missing_docs: list[str] = []

    if not filing.documents:
        errors.append("At least one document must be uploaded")
    if filing.fee_waiver_requested and filing.fee_waiver_granted is None and not any(
        doc.document_type_code == "FEE_WAIVER" for doc in filing.documents
    ):
        missing_docs.append("Completed, signed Fee Waiver Request (MC 20), nonpublic")

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
                FilingRequirement.is_required.is_(True),
            )
        )
        required_docs = list(requirements.scalars().all())

        filed_doc_types = {doc.document_type_code for doc in filing.documents}

        required_docs = requirements_for_filing_type(required_docs, filing.filing_type)
        if filing.filing_type == "subsequent" and not any(
            dt.startswith("MOT_") or dt == "MOTION" for dt in filed_doc_types
        ):
            # An answer or other subsequent paper does not need motion companions.
            required_docs = []

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
                    req.description
                    + (f". See {req.mcr_reference}." if req.mcr_reference else "")
                )

        if not filing.case_title and not filing.case_id:
            errors.append("Case title is required for new case filings")

    # MCR 1.109 text-searchability is advisory at validation.
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


async def check_submission(
    db: AsyncSession,
    filing: FilingEnvelope,
    *, expected_submission_token: str, idempotency_key: str | None,
) -> None:
    if idempotency_key and await db.scalar(select(FilingTransaction.id).where(
        FilingTransaction.filing_id == filing.id,
        FilingTransaction.idempotency_key == idempotency_key,
    )):
        raise SubmissionAlreadyRecordedError(filing)
    if expected_submission_token != filing.submission_token:
        raise FilingSubmissionError(
            409,
            "This filing changed after you opened the review. "
            "Refresh the review and check the saved details and documents "
            "before submitting.",
        )
    if filing.status not in (FilingStatus.DRAFT, FilingStatus.RETURNED):
        raise FilingSubmissionError(400, "Only draft or returned filings can be submitted")
    if not (await fee_state(db, filing)).obligation_met:
        raise FilingSubmissionError(402, "Payment required before submission")
    validation = await validate_filing(db, filing)
    if not validation.is_valid:
        error_parts = []
        if validation.errors:
            error_parts.append("Errors: " + "; ".join(validation.errors))
        if validation.missing_required_documents:
            error_parts.append(
                "Missing documents: " + "; ".join(validation.missing_required_documents)
            )
        raise FilingSubmissionError(
            400, "Filing validation failed. " + " | ".join(error_parts),
        )


async def submit_filing(
    db: AsyncSession,
    filing_id: int,
    *, idempotency_key: str | None = None, expected_submission_token: str | None = None,
) -> FilingEnvelope | None:
    probe = await get_filing(db, filing_id)
    if probe and expected_submission_token is not None:
        await check_submission(
            db, probe, expected_submission_token=expected_submission_token,
            idempotency_key=idempotency_key,
        )
    if not probe or probe.status not in (FilingStatus.DRAFT, FilingStatus.RETURNED):
        return None
    await validate_filing_destination(db, probe, filer_id=probe.filer_id, lock=False)
    await verify_filing_documents(probe)
    fingerprints = [(doc.id, doc.sha256_hash, doc.file_size_bytes) for doc in probe.documents]

    filing = await get_filing(db, filing_id, for_update=True)
    if filing and expected_submission_token is not None:
        await check_submission(
            db, filing, expected_submission_token=expected_submission_token,
            idempotency_key=idempotency_key,
        )
    if not filing or filing.status not in (FilingStatus.DRAFT, FilingStatus.RETURNED):
        return None
    await validate_filing_destination(db, filing, filer_id=filing.filer_id)
    current = [(doc.id, doc.sha256_hash, doc.file_size_bytes) for doc in filing.documents]
    if current != fingerprints:
        raise FilingDocumentError(
            "Stored documents changed after integrity verification. Review the draft and try again."
        )
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


@dataclass(frozen=True)
class ReviewEvidence:
    date_version: int
    ordered_date: bool
    fingerprints: list[tuple[int, str, int]] | None


async def verify_review(
    db: AsyncSession,
    filing_id: int,
    action: Literal["accept", "reject", "return"],
    *,
    expected_submission_count: int,
) -> ReviewEvidence | None:
    # Verify stored bytes before taking the write lock. Re-check cheap metadata after.
    probe = await get_filing(db, filing_id)
    if not probe:
        return None
    if probe.submission_count != expected_submission_count:
        raise StaleFilingReviewError(
            "The filing was resubmitted after this review was opened. Close the review, "
            "refresh the queue and review the new submission before deciding."
        )
    if probe.status not in (FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW):
        return None

    ordered_date = (probe.filing_date_basis or {}).get("source") == "court_order"
    date_version = probe.filing_date_version
    fingerprints: list[tuple[int, str, int]] | None = None
    if action == "accept":
        court_order = None
        if ordered_date:
            basis = probe.filing_date_basis or {}
            court_order = await db.scalar(select(FilingDocument).where(
                FilingDocument.id == basis.get("order_document_id"),
                FilingDocument.envelope_id == probe.id,
                FilingDocument.document_type_code == "FILING_DATE_ORDER",
                FilingDocument.retained_at.is_not(None),
            ))
            if (court_order is None or probe.filing_date is None
                    or basis.get("submission_number") != probe.submission_count):
                raise FilingDateUnavailableError("The filing-date order requires court review")
        await verify_filing_documents(probe, court_order)
        fingerprints = [
            (doc.id, doc.sha256_hash, doc.file_size_bytes) for doc in probe.documents
        ]
        if court_order is not None:
            fingerprints.append(
                (court_order.id, court_order.sha256_hash, court_order.file_size_bytes)
            )
    return ReviewEvidence(date_version, ordered_date, fingerprints)


async def record_review(
    db: AsyncSession,
    filing_id: int,
    reviewer_id: int,
    action: Literal["accept", "reject", "return"],
    reason: str | None = None,
    *,
    expected_submission_count: int,
    evidence: ReviewEvidence,
) -> FilingEnvelope | None:
    ordered_date, fingerprints = evidence.ordered_date, evidence.fingerprints
    filing = await get_filing(db, filing_id, for_update=True)
    if not filing:
        return None
    if filing.submission_count != expected_submission_count:
        raise StaleFilingReviewError(
            "The filing was resubmitted after this review was opened. Close the review, "
            "refresh the queue and review the new submission before deciding."
        )
    if filing.status not in (FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW):
        return None

    case = None
    if action == "accept":
        # A date order recorded during verification must not be replaced by the calendar.
        if filing.filing_date_version != evidence.date_version:
            raise StaleFilingReviewError(
                "The filing date changed while this review was in progress. Refresh the "
                "filing and review its date before deciding."
            )
        case = await validate_filing_destination(db, filing, filer_id=None)
        current = [(doc.id, doc.sha256_hash, doc.file_size_bytes) for doc in filing.documents]
        if ordered_date:
            basis = filing.filing_date_basis or {}
            order = await db.scalar(select(FilingDocument).where(
                FilingDocument.id == basis.get("order_document_id"),
                FilingDocument.envelope_id == filing.id,
            ))
            if order is not None:
                current.append((order.id, order.sha256_hash, order.file_size_bytes))
        if fingerprints is None or current != fingerprints:
            raise FilingDocumentError(
                "Stored documents changed after integrity verification. Open the filing again."
            )

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
        if case is None:
            court_type, code = (await db.execute(
                select(Court.court_type, CaseType.code)
                .join(CaseType, CaseType.court_id == Court.id)
                .where(Court.id == filing.court_id, CaseType.id == filing.case_type_id)
            )).one()
            year = (filing.filing_date or filing.submitted_at).year
            suffix = case_number_code(court_type, code)
            case = Case(
                court_id=filing.court_id,
                case_number=f"{year:04d}-{filing.id:06d}-{suffix}",
                case_type_id=filing.case_type_id,
                title=filing.case_title or "Untitled Case",
                status=CaseStatus.OPEN,
                filed_date=filing.submitted_at,
                filing_date=filing.filing_date,
            )
        cms_result = await submit_filing_to_cms(case.case_number, filing.id)
        if not cms_result.success:
            filing.cms_error = cms_result.error_message or "The submission failed"
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

    await record_transaction(db, filing, filing.status.value, reviewer_id, reason=reason)
    await db.flush()
    await db.refresh(filing)
    await db.refresh(filing, ["documents"])
    return filing


async def review_filing(
    db: AsyncSession,
    filing_id: int,
    reviewer_id: int,
    action: Literal["accept", "reject", "return"],
    reason: str | None = None,
    *,
    expected_submission_count: int,
) -> FilingEnvelope | None:
    evidence = await verify_review(
        db, filing_id, action, expected_submission_count=expected_submission_count,
    )
    if evidence is None:
        return None
    return await record_review(
        db, filing_id, reviewer_id, action, reason,
        expected_submission_count=expected_submission_count, evidence=evidence,
    )


async def lock_filings(db: AsyncSession, filing_ids: list[int]) -> None:
    await db.execute(
        select(FilingEnvelope.id).where(FilingEnvelope.id.in_(filing_ids))
        .order_by(FilingEnvelope.id).with_for_update()
    )


async def get_clerk_queue(
    db: AsyncSession,
    court_id: int,
    page: int = 1,
    page_size: int = 25,
    status: FilingStatus | None = None,
    fee_waivers: bool = False,
    search: str = "",
    waiting_48h_only: bool = False,
) -> ClerkQueueResponse:
    as_of = datetime.now(UTC)
    cutoff = as_of - timedelta(hours=48)
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
    search = search.strip()
    if search.startswith("#") and search[1:].isascii() and search[1:].isdigit():
        filing_id = int(search[1:])
        filters.append(FilingEnvelope.id == filing_id if filing_id <= MAX_RECORD_ID else false())
    elif search:
        filters.append(or_(
            FilingEnvelope.case_title.icontains(search, autoescape=True),
            select(Case.id).where(
                Case.id == FilingEnvelope.case_id,
                Case.case_number.icontains(search, autoescape=True),
            ).exists(),
        ))
    if waiting_48h_only:
        filters.append(FilingEnvelope.submitted_at <= cutoff)
    query = (
        _FILING_SUMMARIES
        .where(*filters)
        .order_by(FilingEnvelope.submitted_at.asc(), FilingEnvelope.id.asc())
    )
    count_query = (
        select(
            func.count().label("total"),
            func.count().filter(FilingEnvelope.status == FilingStatus.SUBMITTED)
                .label("submitted_count"),
            func.count().filter(FilingEnvelope.status == FilingStatus.UNDER_REVIEW)
                .label("under_review_count"),
            func.count().filter(FilingEnvelope.submitted_at <= cutoff).label("waiting_48h"),
            func.min(FilingEnvelope.submitted_at).label("oldest_submitted_at"),
        )
        .select_from(FilingEnvelope)
        .where(*filters)
    )

    counts = (await db.execute(count_query)).one()
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return ClerkQueueResponse(
        filings=[FilingSummary.model_validate(row) for row in result],
        total=counts.total, waiting_48h=counts.waiting_48h,
        submitted_count=counts.submitted_count, under_review_count=counts.under_review_count,
        oldest_submitted_at=counts.oldest_submitted_at, as_of=as_of,
        page=page, page_size=page_size,
    )
