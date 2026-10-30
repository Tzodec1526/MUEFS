"""Tests for filing-related functionality."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.integrations.cms_adapter import CMSFilingResult
from app.models.case import Case, CaseParticipant, CaseStatus
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingStatus
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
        filing_type="initial",
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
async def test_filing_lifecycle(db_session, stored_document):
    user, court, case_type = await create_test_fixtures(db_session)

    # Create
    data = FilingEnvelopeCreate(
        filing_type="initial",
        court_id=court.id,
        case_type_id=case_type.id,
        case_title="Test Case",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)
    assert filing.status == FilingStatus.DRAFT

    doc = stored_document(filing.id)
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
        db_session, filing.id, reviewer_id=clerk.id, action="accept", expected_submission_count=1
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
    assert parts == []  # Acceptance does not establish party roles or restricted-case access.


@pytest.mark.asyncio
async def test_reject_filing(db_session, stored_document):
    user, court, case_type = await create_test_fixtures(db_session)

    data = FilingEnvelopeCreate(
        filing_type="initial",
        court_id=court.id,
        case_type_id=case_type.id,
        case_title="Test Rejection",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)

    # Add doc and submit
    doc = stored_document(filing.id, document_type_code="MOTION", title="Motion")
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
        db_session,
        filing.id,
        reviewer_id=clerk.id,
        action="reject",
        reason="Missing required documents",
        expected_submission_count=1,
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
            filing_type="initial",
            court_id=court.id,
            case_type_id=case_type.id,
            case_title=f"Case {i}",
        )
        await filing_service.create_filing(db_session, user.id, data)

    filings, total, counts = await filing_service.list_filings(db_session, user.id)
    assert counts[FilingStatus.DRAFT] == total
    assert total == 3
    assert len(filings) == 3


@pytest.mark.asyncio
async def test_validate_filing_no_documents(db_session):
    user, court, case_type = await create_test_fixtures(db_session)

    data = FilingEnvelopeCreate(
        filing_type="initial",
        court_id=court.id,
        case_type_id=case_type.id,
        case_title="No Docs Case",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)

    validation = await filing_service.validate_filing(
        db_session, await filing_service.get_filing(db_session, filing.id),
    )
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
        filing_type="subsequent",
    )
    with pytest.raises(filing_service.FilingDestinationError) as exc:
        await filing_service.create_filing(db_session, stranger.id, data)
    assert exc.value.status_code == 403
    assert "participation" in str(exc.value).lower() or "authorized" in str(exc.value).lower()
    from app.services import access_service
    assert await access_service.user_may_read_case(db_session, stranger, case.id) is False


@pytest.mark.asyncio
async def test_create_filing_on_public_case_denied_without_participant(db_session):
    user, court, case_type = await create_test_fixtures(db_session)
    stranger = User(
        email="public-idor@example.com",
        first_name="P",
        last_name="Ublic",
        user_type=UserType.ATTORNEY,
        bar_number="P00001",
        bar_number_verified=True,
    )
    db_session.add(stranger)
    case = Case(
        court_id=court.id,
        case_number="OPEN-IDOR",
        case_type_id=case_type.id,
        title="Public docket",
        status=CaseStatus.OPEN,
        filed_date=datetime.now(UTC),
        is_sealed=False,
    )
    db_session.add(case)
    await db_session.flush()
    from app.services import access_service
    assert await access_service.user_may_read_case(db_session, stranger, case.id) is True
    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_type_id=case_type.id,
        case_id=case.id,
        case_title="Should not attach",
        filing_type="subsequent",
    )
    with pytest.raises(filing_service.FilingDestinationError) as exc:
        await filing_service.create_filing(db_session, stranger.id, data)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_filing_on_public_case_denied_when_access_disabled(db_session):
    from app.models.case import CaseParticipant, ParticipantRole

    user, court, case_type = await create_test_fixtures(db_session)
    user.bar_number_verified = True
    case = Case(
        court_id=court.id,
        case_number="OPEN-REVOKED",
        case_type_id=case_type.id,
        title="Public docket",
        status=CaseStatus.OPEN,
        filed_date=datetime.now(UTC),
        is_sealed=False,
    )
    db_session.add(case)
    await db_session.flush()
    db_session.add(CaseParticipant(
        case_id=case.id,
        user_id=user.id,
        role=ParticipantRole.ATTORNEY,
        party_name="Counsel",
        attorney_bar_number=user.bar_number,
        is_active=True,
        access_enabled=False,
        reviewed_at=datetime.now(UTC),
    ))
    await db_session.flush()
    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_type_id=case_type.id,
        case_id=case.id,
        case_title="Motion",
        filing_type="subsequent",
    )
    with pytest.raises(filing_service.FilingDestinationError) as exc:
        await filing_service.create_filing(db_session, user.id, data)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_filing_on_public_case_allowed_with_reviewed_participant(
    db_session, api_client,
):
    from app.models.case import CaseParticipant, ParticipantRole

    user, court, case_type = await create_test_fixtures(db_session)
    user.bar_number_verified = True
    case = Case(
        court_id=court.id,
        case_number="OPEN-OK",
        case_type_id=case_type.id,
        title="Public docket",
        status=CaseStatus.OPEN,
        filed_date=datetime.now(UTC),
        is_sealed=False,
    )
    db_session.add(case)
    await db_session.flush()
    db_session.add(CaseParticipant(
        case_id=case.id,
        user_id=user.id,
        role=ParticipantRole.ATTORNEY,
        party_name="Counsel",
        attorney_bar_number=user.bar_number,
        is_active=True,
        access_enabled=True,
        reviewed_at=datetime.now(UTC),
    ))
    await db_session.flush()
    data = FilingEnvelopeCreate(
        court_id=court.id,
        case_type_id=case_type.id,
        case_id=case.id,
        case_title="Motion",
        filing_type="subsequent",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)
    assert filing.case_id == case.id
    # Queues and receipts identify the case by the court's caption, not the client's.
    assert filing.case_title == "Public docket"
    path = f"/api/v1/cases/{case.id}"
    assert (await api_client.get(path)).json()["can_file"] is False
    api_client.headers["X-Demo-User-Id"] = str(user.id)
    assert (await api_client.get(path)).json()["can_file"] is True
    participant = await db_session.scalar(select(CaseParticipant).where(
        CaseParticipant.case_id == case.id,
    ))
    participant.access_enabled = False
    await db_session.flush()
    assert (await api_client.get(path)).json()["can_file"] is False

    edit = {"expected_details_token": filing.details_token}
    url = f"/api/v1/filings/{filing.id}"
    renamed = await api_client.patch(url, json={**edit, "case_title": "Another case"})
    assert renamed.status_code == 409, renamed.text
    unchanged = await api_client.patch(url, json={**edit, "case_title": "Public docket"})
    assert unchanged.status_code == 200, unchanged.text


@pytest.mark.asyncio
async def test_accept_records_only_when_cms_not_configured(
    db_session, monkeypatch, stored_document,
):
    from app.config import settings
    from app.integrations.cms_adapter import submit_filing_to_cms

    monkeypatch.setattr(settings, "allow_demo_mode", False)
    result = await submit_filing_to_cms("MI-1-2026-000001", 42)
    assert result.success is True
    assert result.cms_filing_id is None
    assert result.cms_case_number == "MI-1-2026-000001"

    monkeypatch.setattr(settings, "allow_demo_mode", True)
    user, court, case_type = await create_test_fixtures(db_session)
    data = FilingEnvelopeCreate(
        filing_type="initial",
        court_id=court.id,
        case_type_id=case_type.id,
        case_title="Records Only Path",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)
    db_session.add(stored_document(filing.id))
    await db_session.flush()
    await filing_service.submit_filing(db_session, filing.id)

    async def records_only(case_number, filing_id):
        return CMSFilingResult(success=True, cms_case_number=case_number, cms_filing_id=None)

    monkeypatch.setattr("app.services.filing_service.submit_filing_to_cms", records_only)
    clerk = User(
        email="clerk-records@example.com",
        first_name="C",
        last_name="Lerk",
        user_type=UserType.CLERK,
    )
    db_session.add(clerk)
    await db_session.flush()
    reviewed = await filing_service.review_filing(
        db_session, filing.id, reviewer_id=clerk.id, action="accept", expected_submission_count=1,
    )
    assert reviewed is not None
    assert reviewed.status == FilingStatus.ACCEPTED
    assert reviewed.cms_error is None
    assert reviewed.cms_filing_id is None


@pytest.mark.asyncio
async def test_accept_does_not_mark_accepted_when_cms_fails(
    db_session, monkeypatch, stored_document,
):
    user, court, case_type = await create_test_fixtures(db_session)
    data = FilingEnvelopeCreate(
        filing_type="initial",
        court_id=court.id,
        case_type_id=case_type.id,
        case_title="CMS Fail",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)
    db_session.add(stored_document(filing.id))
    await db_session.flush()
    await filing_service.submit_filing(db_session, filing.id)

    async def fail_submission(_case_number, _filing_id):
        return CMSFilingResult(success=False, error_message="JIS unavailable")

    monkeypatch.setattr("app.services.filing_service.submit_filing_to_cms", fail_submission)
    clerk = User(
        email="clerk-cms@example.com",
        first_name="C",
        last_name="Lerk",
        user_type=UserType.CLERK,
    )
    db_session.add(clerk)
    await db_session.flush()
    reviewed = await filing_service.review_filing(
        db_session, filing.id, reviewer_id=clerk.id, action="accept", expected_submission_count=1
    )
    assert reviewed is not None
    assert reviewed.status != FilingStatus.ACCEPTED
    assert reviewed.cms_error == "JIS unavailable"


@pytest.mark.asyncio
async def test_accept_does_not_decide_requested_fee_waiver(db_session, stored_document):
    user, court, case_type = await create_test_fixtures(db_session)
    data = FilingEnvelopeCreate(
        filing_type="initial",
        court_id=court.id,
        case_type_id=case_type.id,
        case_title="IFP",
        fee_waiver_requested=True,
        fee_waiver_reason="Indigent",
    )
    filing = await filing_service.create_filing(db_session, user.id, data)
    db_session.add(stored_document(filing.id))
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
        db_session, filing.id, reviewer_id=clerk.id, action="accept", expected_submission_count=1
    )
    assert accepted is not None
    assert accepted.fee_waiver_granted is None
    assert accepted.status == FilingStatus.ACCEPTED

