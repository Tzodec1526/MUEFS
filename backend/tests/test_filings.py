"""Tests for filing-related functionality."""

import pytest
from sqlalchemy import select

from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
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
        filing_fee_cents=17500,
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
