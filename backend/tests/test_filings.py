"""Tests for filing-related functionality."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.integrations.cms_adapter import CMSFilingResult
from app.models.case import Case, CaseParticipant, CaseStatus
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingDocument, FilingStatus
from app.models.user import User, UserType
from app.schemas.filing import FilingEnvelopeCreate
from app.services import filing_service


async def create_test_fixtures(db_session):
    """Create common test fixtures."""
    user = User(
        email="test@example.com",
        first_name="Test",
        last_name="Attorney",
        user_type=UserType.ATTORNEY,
        bar_number="P99999",
    )
    db_session.add(user)

    court = Court(
        name="Test Circuit Court",
        county="Test",
        court_type=CourtType.CIRCUIT,
    )
    db_session.add(court)
    await db_session.flush()

    case_type = CaseType(
        court_id=court.id,
        code="CIV",
        name="Civil",
        category=CaseCategory.CIVIL,
        filing_fee_cents=15000,
    )
    db_session.add(case_type)
    await db_session.flush()

    return user, court, case_type


@pytest.mark.asyncio
async def test_create_filing(db_session):
    user, court, case_type = await create_test_fixtures(db_session)

    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_type_id=case_type.id,
        case_title="Smith v. Jones",
        filing_description="Initial complaint for breach of contract",
    )

    filing = await filing_service.create_filing(db_session, user.id, data)

    assert filing.id is not None
    assert filing.court_id == court.id
    assert filing.filer_id == user.id
    assert filing.status == FilingStatus.DRAFT
    assert filing.case_title == "Smith v. Jones"


@pytest.mark.asyncio
async def test_filing_lifecycle(db_session):
    user, court, case_type = await create_test_fixtures(db_session)

    # Create
    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_type_id=case_type.id,
        case_title="Test Case",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)
    assert filing.status == FilingStatus.DRAFT

    # Add a document (directly, bypassing S3)
    doc = FilingDocument(
        envelope_id=filing.id,
        document_type_code="COMPLAINT",
        title="Complaint",
        file_key="test/complaint.pdf",
        file_size_bytes=1024,
        mime_type="application/pdf",
        sha256_hash="abc123",
        is_text_searchable=True,
    )
    db_session.add(doc)
    await db_session.flush()

    # Submit
    submitted = await filing_service.submit_filing(db_session, filing.id)
    assert submitted is not None
    assert submitted.status == FilingStatus.SUBMITTED
    assert submitted.submitted_at is not None

    # Review - Accept
    clerk = User(
        email="clerk@example.com",
        first_name="Test",
        last_name="Clerk",
        user_type=UserType.CLERK,
    )
    db_session.add(clerk)
    await db_session.flush()

    accepted = await filing_service.review_filing(
        db_session, filing.id, reviewer_id=clerk.id, action="accept"
    )
    assert accepted is not None
    assert accepted.status == FilingStatus.ACCEPTED
    assert accepted.case_id is not None  # Case should be created
    assert accepted.cms_filing_id is not None
    assert accepted.cms_error is None
    part_q = await db_session.execute(
        select(CaseParticipant).where(CaseParticipant.case_id == accepted.case_id)
    )
    parts = list(part_q.scalars().all())
    assert any(p.user_id == user.id for p in parts)


@pytest.mark.asyncio
async def test_reject_filing(db_session):
    user, court, case_type = await create_test_fixtures(db_session)

    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_type_id=case_type.id,
        case_title="Test Rejection",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)

    # Add doc and submit
    doc = FilingDocument(
        envelope_id=filing.id,
        document_type_code="MOTION",
        title="Motion",
        file_key="test/motion.pdf",
        file_size_bytes=512,
        mime_type="application/pdf",
        sha256_hash="def456",
        is_text_searchable=True,
    )
    db_session.add(doc)
    await db_session.flush()

    await filing_service.submit_filing(db_session, filing.id)

    clerk = User(
        email="clerk2@example.com",
        first_name="Test",
        last_name="Clerk",
        user_type=UserType.CLERK,
    )
    db_session.add(clerk)
    await db_session.flush()

    rejected = await filing_service.review_filing(
        db_session, filing.id, reviewer_id=clerk.id,
        action="reject", reason="Missing required documents",
    )
    assert rejected is not None
    assert rejected.status == FilingStatus.REJECTED
    assert rejected.rejection_reason == "Missing required documents"


@pytest.mark.asyncio
async def test_list_filings(db_session):
    user, court, case_type = await create_test_fixtures(db_session)

    # Create multiple filings
    for i in range(3):
        data = FilingEnvelopeCreate(
            court_id=court.id,
            case_type_id=case_type.id,
            case_title=f"Case {i}",
        )
        await filing_service.create_filing(db_session, user.id, data)

    filings, total = await filing_service.list_filings(db_session, user.id)
    assert total == 3
    assert len(filings) == 3


@pytest.mark.asyncio
async def test_validate_filing_no_documents(db_session):
    user, court, case_type = await create_test_fixtures(db_session)

    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_type_id=case_type.id,
        case_title="No Docs Case",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)

    validation = await filing_service.validate_filing(db_session, filing.id)
    assert validation.is_valid is False
    assert any("document" in e.lower() for e in validation.errors)


def _req(code: str) -> SimpleNamespace:
    """Lightweight stand-in for a FilingRequirement row (only the code matters)."""
    return SimpleNamespace(document_type_code=code)


def test_requirements_for_filing_type_initial_keeps_only_initiating_docs():
    reqs = [
        _req(c)
        for c in (
            "COMPLAINT", "SUMMONS", "PROOF_SERVICE", "MOTION", "BRIEF",
            "MOT_RECONSIDER", "NOTICE_HEARING", "NOT_HEARING", "DISC_CERT_GF",
            "ANSWER", "REPLY", "CERT_SERVICE", "EXHIBIT", "JURY_DEMAND",
        )
    ]
    kept = {
        r.document_type_code
        for r in filing_service.requirements_for_filing_type(reqs, "initial")
    }
    # Motion companions, responsive docs, and proof/cert of service are dropped --
    # service happens after the case is filed (MCR 2.104 / 2.107).
    assert kept == {"COMPLAINT", "SUMMONS", "EXHIBIT", "JURY_DEMAND"}


def test_requirements_for_filing_type_motion_keeps_only_motion_companions():
    reqs = [
        _req(c)
        for c in ("COMPLAINT", "SUMMONS", "MOTION", "BRIEF", "MOT_TRO", "PROOF_SERVICE", "EXHIBIT")
    ]
    for ftype in ("subsequent", "motion"):
        kept = {
            r.document_type_code
            for r in filing_service.requirements_for_filing_type(reqs, ftype)
        }
        assert kept == {"MOTION", "BRIEF", "MOT_TRO"}, ftype


def test_requirements_for_filing_type_other_returns_all_unfiltered():
    reqs = [_req("COMPLAINT"), _req("MOTION"), _req("PROOF_SERVICE")]
    kept = [
        r.document_type_code
        for r in filing_service.requirements_for_filing_type(reqs, "service_only")
    ]
    assert kept == ["COMPLAINT", "MOTION", "PROOF_SERVICE"]


@pytest.mark.asyncio
async def test_create_filing_on_sealed_case_denied_to_stranger(db_session):
    user, court, case_type = await create_test_fixtures(db_session)
    stranger = User(
        email="idor@example.com",
        first_name="I",
        last_name="Dor",
        user_type=UserType.ATTORNEY,
        bar_number="P00000",
    )
    db_session.add(stranger)
    case = Case(
        court_id=court.id,
        case_number="SEAL-IDOR",
        case_type_id=case_type.id,
        title="Sealed",
        status=CaseStatus.OPEN,
        filed_date=datetime.now(UTC),
        is_sealed=True,
    )
    db_session.add(case)
    await db_session.flush()
    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_type_id=case_type.id,
        case_id=case.id,
        case_title="Should not attach",
    )
    with pytest.raises(filing_service.FilingCreateError) as exc:
        await filing_service.create_filing(db_session, stranger.id, data)
    assert exc.value.status_code == 403
    assert await db_session.get(Case, case.id)
    from app.services import access_service
    assert await access_service.user_may_read_case(db_session, stranger.id, case.id) is False


@pytest.mark.asyncio
async def test_accept_does_not_mark_accepted_when_cms_fails(db_session, monkeypatch):
    user, court, case_type = await create_test_fixtures(db_session)
    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_type_id=case_type.id,
        case_title="CMS Fail",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)
    db_session.add(FilingDocument(
        envelope_id=filing.id,
        document_type_code="COMPLAINT",
        title="Complaint",
        file_key="test/cms-fail.pdf",
        file_size_bytes=1024,
        mime_type="application/pdf",
        sha256_hash="cmsfail",
        is_text_searchable=True,
    ))
    await db_session.flush()
    await filing_service.submit_filing(db_session, filing.id)

    class FailingAdapter:
        async def submit_filing(self, **_kwargs):
            return CMSFilingResult(success=False, error_message="JIS unavailable")

    monkeypatch.setattr(
        "app.services.filing_service.get_cms_adapter",
        lambda _cms_type: FailingAdapter(),
    )
    clerk = User(
        email="clerk-cms@example.com",
        first_name="C",
        last_name="Lerk",
        user_type=UserType.CLERK,
    )
    db_session.add(clerk)
    await db_session.flush()
    reviewed = await filing_service.review_filing(
        db_session, filing.id, reviewer_id=clerk.id, action="accept"
    )
    assert reviewed is not None
    assert reviewed.status != FilingStatus.ACCEPTED
    assert reviewed.cms_error == "JIS unavailable"


@pytest.mark.asyncio
async def test_accept_grants_requested_fee_waiver(db_session):
    user, court, case_type = await create_test_fixtures(db_session)
    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_type_id=case_type.id,
        case_title="IFP",
        fee_waiver_requested=True,
        fee_waiver_reason="Indigent",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)
    db_session.add(FilingDocument(
        envelope_id=filing.id,
        document_type_code="COMPLAINT",
        title="Complaint",
        file_key="test/ifp.pdf",
        file_size_bytes=1024,
        mime_type="application/pdf",
        sha256_hash="ifp",
        is_text_searchable=True,
    ))
    await db_session.flush()
    await filing_service.submit_filing(db_session, filing.id)
    clerk = User(
        email="clerk-ifp@example.com",
        first_name="C",
        last_name="Lerk",
        user_type=UserType.CLERK,
    )
    db_session.add(clerk)
    await db_session.flush()
    accepted = await filing_service.review_filing(
        db_session, filing.id, reviewer_id=clerk.id, action="accept"
    )
    assert accepted is not None
    assert accepted.fee_waiver_granted is True
    assert accepted.status == FilingStatus.ACCEPTED

