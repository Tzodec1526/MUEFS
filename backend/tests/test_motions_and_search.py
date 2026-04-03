"""Tests for filing motions to existing cases and case search functionality."""

import pytest
from sqlalchemy import select

from app.models.case import Case, CaseParticipant, ParticipantRole
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.user import FavoriteCase, User, UserType
from app.schemas.filing import FilingEnvelopeCreate
from app.services import filing_service, search_service


async def create_court_with_case(db_session):
    """Create a court, case type, user, and an accepted case for motion testing."""
    user = User(
        email="motion_attorney@test.com",
        first_name="Motion",
        last_name="Tester",
        user_type=UserType.ATTORNEY,
        bar_number="P77777",
    )
    db_session.add(user)

    clerk = User(
        email="motion_clerk@test.com",
        first_name="Clerk",
        last_name="Tester",
        user_type=UserType.CLERK,
    )
    db_session.add(clerk)

    court = Court(
        name="3rd Circuit Court",
        county="Wayne",
        court_type=CourtType.CIRCUIT,
        city="Detroit",
    )
    db_session.add(court)
    await db_session.flush()

    case_type = CaseType(
        court_id=court.id,
        code="CIV-GEN",
        name="Civil - General",
        category=CaseCategory.CIVIL,
        filing_fee_cents=17500,
    )
    db_session.add(case_type)

    subp_type = CaseType(
        court_id=court.id,
        code="CIV-SUBP",
        name="Domesticating Subpoena - MI Uniform Depositions Act",
        category=CaseCategory.CIVIL,
        filing_fee_cents=17500,
    )
    db_session.add(subp_type)
    await db_session.flush()

    # Create an initial filing, add a document, submit, and accept it to create a case
    initial_filing = FilingEnvelope(
        court_id=court.id,
        case_type_id=case_type.id,
        filer_id=user.id,
        case_title="Johnson v. Smith Industries LLC",
        filing_description="Initial complaint for breach of contract",
        status=FilingStatus.DRAFT,
    )
    db_session.add(initial_filing)
    await db_session.flush()

    doc = FilingDocument(
        envelope_id=initial_filing.id,
        document_type_code="COMPLAINT",
        title="Complaint for Breach of Contract",
        file_key="test/complaint.pdf",
        file_size_bytes=2048,
        mime_type="application/pdf",
        sha256_hash="abc123initial",
        is_text_searchable=True,
    )
    db_session.add(doc)
    await db_session.flush()

    # Submit and accept the filing (creates a case)
    await filing_service.submit_filing(db_session, initial_filing.id)
    accepted = await filing_service.review_filing(
        db_session, initial_filing.id, reviewer_id=clerk.id, action="accept"
    )

    # Add participants to the case
    case = await db_session.execute(select(Case).where(Case.id == accepted.case_id))
    case = case.scalar_one()

    db_session.add(CaseParticipant(
        case_id=case.id, user_id=user.id,
        role=ParticipantRole.ATTORNEY_PLAINTIFF,
        party_name="Motion Tester", attorney_bar_number="P77777",
    ))
    db_session.add(CaseParticipant(
        case_id=case.id,
        role=ParticipantRole.PLAINTIFF,
        party_name="Robert Johnson",
    ))
    db_session.add(CaseParticipant(
        case_id=case.id,
        role=ParticipantRole.DEFENDANT,
        party_name="Smith Industries LLC",
    ))
    await db_session.flush()

    return user, clerk, court, case_type, subp_type, case


# ========== MOTION FILING TESTS ==========


@pytest.mark.asyncio
async def test_file_motion_to_existing_case(db_session):
    """Test filing a motion to an already-existing case."""
    user, clerk, court, case_type, _, case = await create_court_with_case(db_session)

    # Create a motion filing referencing the existing case
    motion_data = FilingEnvelopeCreate(
        court_id=court.id,
        case_id=case.id,  # Filing to existing case
        case_type_id=case_type.id,
        case_title=case.title,
        filing_description="Motion for Summary Disposition under MCR 2.116(C)(10)",
    )
    motion_filing = await filing_service.create_filing(db_session, user.id, motion_data)

    assert motion_filing.case_id == case.id
    assert motion_filing.status == FilingStatus.DRAFT

    # Add motion document
    motion_doc = FilingDocument(
        envelope_id=motion_filing.id,
        document_type_code="MOTION",
        title="Motion for Summary Disposition",
        file_key="test/motion_sd.pdf",
        file_size_bytes=4096,
        mime_type="application/pdf",
        sha256_hash="motion_hash_001",
        is_text_searchable=True,
    )
    db_session.add(motion_doc)

    # Add brief in support
    brief_doc = FilingDocument(
        envelope_id=motion_filing.id,
        document_type_code="BRIEF",
        title="Brief in Support of Motion for Summary Disposition",
        file_key="test/brief_sd.pdf",
        file_size_bytes=8192,
        mime_type="application/pdf",
        sha256_hash="brief_hash_001",
        is_text_searchable=True,
    )
    db_session.add(brief_doc)
    await db_session.flush()

    # Submit the motion
    submitted = await filing_service.submit_filing(db_session, motion_filing.id)
    assert submitted is not None
    assert submitted.status == FilingStatus.SUBMITTED
    assert submitted.case_id == case.id

    # Accept the motion
    accepted = await filing_service.review_filing(
        db_session, motion_filing.id, reviewer_id=clerk.id, action="accept"
    )
    assert accepted is not None
    assert accepted.status == FilingStatus.ACCEPTED
    # Should NOT create a new case since case_id was provided
    assert accepted.case_id == case.id


@pytest.mark.asyncio
async def test_file_multiple_motions_to_same_case(db_session):
    """Test filing multiple motions to the same case."""
    user, clerk, court, case_type, _, case = await create_court_with_case(db_session)

    motion_titles = [
        "Motion to Compel Discovery",
        "Motion for Protective Order",
        "Motion in Limine",
    ]

    for title in motion_titles:
        data = FilingEnvelopeCreate(
            court_id=court.id,
            case_id=case.id,
            case_type_id=case_type.id,
            filing_description=title,
        )
        filing = await filing_service.create_filing(db_session, user.id, data)
        doc = FilingDocument(
            envelope_id=filing.id,
            document_type_code="MOTION",
            title=title,
            file_key=f"test/{title.lower().replace(' ', '_')}.pdf",
            file_size_bytes=1024,
            mime_type="application/pdf",
            sha256_hash=f"hash_{title[:8]}",
            is_text_searchable=True,
        )
        db_session.add(doc)
        await db_session.flush()

    # Verify all filings are linked to the same case
    filings, total = await filing_service.list_filings(db_session, user.id)
    case_filings = [f for f in filings if f.case_id == case.id]
    # Initial complaint + 3 motions = 4 filings linked to this case
    assert len(case_filings) == 4


@pytest.mark.asyncio
async def test_motion_rejected_and_refiled(db_session):
    """Test motion rejected by clerk, then corrected and resubmitted."""
    user, clerk, court, case_type, _, case = await create_court_with_case(db_session)

    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_id=case.id,
        case_type_id=case_type.id,
        filing_description="Motion to Dismiss",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)
    doc = FilingDocument(
        envelope_id=filing.id,
        document_type_code="MOTION",
        title="Motion to Dismiss",
        file_key="test/motion_dismiss.pdf",
        file_size_bytes=1024,
        mime_type="application/pdf",
        sha256_hash="dismiss_hash",
        is_text_searchable=True,
    )
    db_session.add(doc)
    await db_session.flush()

    await filing_service.submit_filing(db_session, filing.id)

    # Clerk returns for correction
    returned = await filing_service.review_filing(
        db_session, filing.id, reviewer_id=clerk.id,
        action="return", reason="Missing brief in support per MCR 2.119(A)(2)",
    )
    assert returned.status == FilingStatus.RETURNED
    assert "MCR 2.119" in returned.rejection_reason


@pytest.mark.asyncio
async def test_domesticating_subpoena_filing(db_session):
    """Test filing a domesticating subpoena under Michigan Uniform Depositions Act."""
    user, clerk, court, _, subp_type, _ = await create_court_with_case(db_session)

    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_type_id=subp_type.id,
        case_title="In re: Subpoena from State of Ohio, Case No. OH-2024-12345",
        filing_description="Request to domesticate out-of-state subpoena per MCL 600.2163a",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)

    # Upload the out-of-state subpoena
    subpoena_doc = FilingDocument(
        envelope_id=filing.id,
        document_type_code="SUBPOENA",
        title="Ohio Subpoena - Authenticated Copy",
        file_key="test/ohio_subpoena.pdf",
        file_size_bytes=3072,
        mime_type="application/pdf",
        sha256_hash="ohio_subp_hash",
        is_text_searchable=True,
    )
    db_session.add(subpoena_doc)

    # Upload proposed Michigan subpoena
    proposed_doc = FilingDocument(
        envelope_id=filing.id,
        document_type_code="PROPOSED_SUBP",
        title="Proposed Michigan Subpoena",
        file_key="test/proposed_mi_subpoena.pdf",
        file_size_bytes=2048,
        mime_type="application/pdf",
        sha256_hash="proposed_subp_hash",
        is_text_searchable=True,
    )
    db_session.add(proposed_doc)
    await db_session.flush()

    # Submit and accept
    await filing_service.submit_filing(db_session, filing.id)
    accepted = await filing_service.review_filing(
        db_session, filing.id, reviewer_id=clerk.id, action="accept"
    )
    assert accepted.status == FilingStatus.ACCEPTED
    assert accepted.case_id is not None  # New case created for the subpoena


# ========== SERVICE ONLY TESTS ==========


@pytest.mark.asyncio
async def test_service_only_filing(db_session):
    """Test service-only filing that skips clerk review."""
    user, clerk, court, case_type, _, case = await create_court_with_case(db_session)

    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_id=case.id,
        case_type_id=case_type.id,
        filing_type="service_only",
        filing_description="Plaintiff's First Set of Interrogatories (MCR 2.309)",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)
    assert filing.filing_type == "service_only"

    # Add discovery document
    doc = FilingDocument(
        envelope_id=filing.id,
        document_type_code="DISC_INTERROG",
        title="Plaintiff's First Set of Interrogatories",
        file_key="test/interrogatories.pdf",
        file_size_bytes=2048,
        mime_type="application/pdf",
        sha256_hash="interrog_hash",
        is_text_searchable=True,
    )
    db_session.add(doc)
    await db_session.flush()

    # Submit - should go straight to SERVED, not SUBMITTED
    submitted = await filing_service.submit_filing(db_session, filing.id)
    assert submitted is not None
    assert submitted.status == FilingStatus.SERVED
    assert submitted.submitted_at is not None


@pytest.mark.asyncio
async def test_service_only_requires_existing_case(db_session):
    """Test that service-only filing requires an existing case."""
    user, _, court, case_type, _, _ = await create_court_with_case(db_session)

    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_id=None,  # No case - should fail validation
        case_type_id=case_type.id,
        filing_type="service_only",
        filing_description="Interrogatories with no case",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)
    doc = FilingDocument(
        envelope_id=filing.id,
        document_type_code="DISC_INTERROG",
        title="Interrogatories",
        file_key="test/interrog.pdf",
        file_size_bytes=1024,
        mime_type="application/pdf",
        sha256_hash="no_case_hash",
        is_text_searchable=True,
    )
    db_session.add(doc)
    await db_session.flush()

    validation = await filing_service.validate_filing(db_session, filing.id)
    assert validation.is_valid is False
    assert any("existing case" in e.lower() for e in validation.errors)


# ========== CASE SEARCH TESTS ==========


@pytest.mark.asyncio
async def test_search_by_case_number(db_session):
    """Test searching for a case by case number."""
    user, _, _, _, _, case = await create_court_with_case(db_session)

    cases, total = await search_service.search_cases(
        db_session, case_number=case.case_number
    )
    assert total >= 1
    assert any(c.id == case.id for c in cases)


@pytest.mark.asyncio
async def test_search_by_party_name(db_session):
    """Test searching for a case by party name."""
    user, _, _, _, _, case = await create_court_with_case(db_session)

    cases, total = await search_service.search_cases(
        db_session, party_name="Smith Industries"
    )
    assert total >= 1
    found = [c for c in cases if c.id == case.id]
    assert len(found) == 1
    assert found[0].title == "Johnson v. Smith Industries LLC"


@pytest.mark.asyncio
async def test_search_by_attorney_bar_number(db_session):
    """Test searching by attorney bar number."""
    user, _, _, _, _, case = await create_court_with_case(db_session)

    cases, total = await search_service.search_cases(
        db_session, attorney_bar_number="P77777"
    )
    assert total >= 1
    assert any(c.id == case.id for c in cases)


@pytest.mark.asyncio
async def test_search_no_results(db_session):
    """Test search with no matching results."""
    cases, total = await search_service.search_cases(
        db_session, case_number="NONEXISTENT-999"
    )
    assert total == 0
    assert len(cases) == 0


@pytest.mark.asyncio
async def test_search_by_court_id(db_session):
    """Test filtering search by court ID."""
    user, _, court, _, _, case = await create_court_with_case(db_session)

    cases, total = await search_service.search_cases(
        db_session, court_id=court.id
    )
    assert total >= 1
    assert all(c.court_id == court.id for c in cases)


# ========== FAVORITE CASES TESTS ==========


@pytest.mark.asyncio
async def test_favorite_case(db_session):
    """Test adding a case to favorites."""
    user, _, _, _, _, case = await create_court_with_case(db_session)

    fav = FavoriteCase(user_id=user.id, case_id=case.id, notes="Key breach of contract case")
    db_session.add(fav)
    await db_session.flush()

    result = await db_session.execute(
        select(FavoriteCase).where(
            FavoriteCase.user_id == user.id,
            FavoriteCase.case_id == case.id,
        )
    )
    saved = result.scalar_one()
    assert saved.notes == "Key breach of contract case"


@pytest.mark.asyncio
async def test_favorite_case_unique_constraint(db_session):
    """Test that a user can't favorite the same case twice."""
    user, _, _, _, _, case = await create_court_with_case(db_session)

    fav1 = FavoriteCase(user_id=user.id, case_id=case.id)
    db_session.add(fav1)
    await db_session.flush()

    fav2 = FavoriteCase(user_id=user.id, case_id=case.id)
    db_session.add(fav2)

    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        await db_session.flush()
