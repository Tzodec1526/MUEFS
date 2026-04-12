"""Authorization helpers for case and document access."""

from datetime import UTC, datetime

import pytest

from app.models.case import Case, CaseParticipant, CaseStatus, ParticipantRole
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import access_service


@pytest.mark.asyncio
async def test_case_access_party_by_user_id(db_session):
    user = User(
        email="party@test.com", first_name="P", last_name="arty",
        user_type=UserType.SELF_REPRESENTED,
    )
    other = User(
        email="other@test.com", first_name="O", last_name="ther",
        user_type=UserType.ATTORNEY,
    )
    db_session.add_all([user, other])
    court = Court(name="Test Court", county="X", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()
    ct = CaseType(
        court_id=court.id, code="C", name="Civil",
        category=CaseCategory.CIVIL, filing_fee_cents=100,
    )
    db_session.add(ct)
    await db_session.flush()
    case = Case(
        court_id=court.id, case_number="T-1", case_type_id=ct.id,
        title="A v B", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
    )
    db_session.add(case)
    await db_session.flush()
    db_session.add(CaseParticipant(
        case_id=case.id, user_id=user.id, role=ParticipantRole.PLAINTIFF,
        party_name="Party Person",
    ))
    await db_session.flush()

    assert await access_service.user_may_read_case(db_session, user.id, case.id) is True
    # Non-sealed: any authenticated user may view the docket (public transparency).
    assert await access_service.user_may_read_case(db_session, other.id, case.id) is True


@pytest.mark.asyncio
async def test_case_access_court_staff(db_session):
    clerk = User(
        email="clerk2@test.com", first_name="C", last_name="lerk",
        user_type=UserType.CLERK,
    )
    db_session.add(clerk)
    court = Court(name="Staff Court", county="Y", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()
    db_session.add(UserCourtRole(
        user_id=clerk.id, court_id=court.id, role=CourtRole.CLERK,
    ))
    ct = CaseType(
        court_id=court.id, code="C", name="Civil",
        category=CaseCategory.CIVIL, filing_fee_cents=100,
    )
    db_session.add(ct)
    await db_session.flush()
    case = Case(
        court_id=court.id, case_number="S-1", case_type_id=ct.id,
        title="X v Y", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
    )
    db_session.add(case)
    await db_session.flush()

    assert await access_service.user_may_read_case(db_session, clerk.id, case.id) is True


@pytest.mark.asyncio
async def test_document_confidential_filer_only(db_session):
    filer = User(
        email="filer@test.com", first_name="F", last_name="iler",
        user_type=UserType.ATTORNEY, bar_number="P111",
    )
    stranger = User(
        email="stranger@test.com", first_name="S", last_name="tranger",
        user_type=UserType.ATTORNEY, bar_number="P222",
    )
    db_session.add_all([filer, stranger])
    court = Court(name="Doc Court", county="Z", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()
    ct = CaseType(
        court_id=court.id, code="C", name="Civil",
        category=CaseCategory.CIVIL, filing_fee_cents=100,
    )
    db_session.add(ct)
    await db_session.flush()
    case = Case(
        court_id=court.id, case_number="D-1", case_type_id=ct.id,
        title="C v D", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
    )
    db_session.add(case)
    await db_session.flush()
    env = FilingEnvelope(
        court_id=court.id, case_id=case.id, case_type_id=ct.id,
        filer_id=filer.id, status=FilingStatus.ACCEPTED,
    )
    db_session.add(env)
    await db_session.flush()
    doc = FilingDocument(
        envelope_id=env.id, document_type_code="X", title="Sealed",
        file_key="k", file_size_bytes=1, mime_type="application/pdf",
        sha256_hash="0" * 64, is_confidential=True,
    )
    db_session.add(doc)
    await db_session.flush()

    assert await access_service.user_may_read_document(db_session, filer.id, doc) is True
    assert await access_service.user_may_read_document(db_session, stranger.id, doc) is False


@pytest.mark.asyncio
async def test_sealed_case_stranger_denied(db_session):
    party = User(
        email="sealed_party@test.com", first_name="P", last_name="arty",
        user_type=UserType.SELF_REPRESENTED,
    )
    stranger = User(
        email="sealed_out@test.com", first_name="S", last_name="tranger",
        user_type=UserType.PUBLIC,
    )
    db_session.add_all([party, stranger])
    court = Court(name="Seal Court", county="S", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()
    ct = CaseType(
        court_id=court.id, code="C", name="Civil",
        category=CaseCategory.CIVIL, filing_fee_cents=100,
    )
    db_session.add(ct)
    await db_session.flush()
    case = Case(
        court_id=court.id, case_number="SEAL-1", case_type_id=ct.id,
        title="Sealed matter", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
        is_sealed=True,
    )
    db_session.add(case)
    await db_session.flush()
    db_session.add(CaseParticipant(
        case_id=case.id, user_id=party.id, role=ParticipantRole.PLAINTIFF,
        party_name="Party Person",
    ))
    await db_session.flush()

    assert await access_service.user_may_read_case(db_session, party.id, case.id) is True
    assert await access_service.user_may_read_case(db_session, stranger.id, case.id) is False


@pytest.mark.asyncio
async def test_public_user_reads_non_sealed_case(db_session):
    viewer = User(
        email="pub_view@test.com", first_name="A", last_name="Viewer",
        user_type=UserType.PUBLIC,
    )
    db_session.add(viewer)
    court = Court(name="Pub Court", county="P", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()
    ct = CaseType(
        court_id=court.id, code="C", name="Civil",
        category=CaseCategory.CIVIL, filing_fee_cents=100,
    )
    db_session.add(ct)
    await db_session.flush()
    case = Case(
        court_id=court.id, case_number="PUB-1", case_type_id=ct.id,
        title="Open matter", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
        is_sealed=False,
    )
    db_session.add(case)
    await db_session.flush()
    assert await access_service.user_may_read_case(db_session, viewer.id, case.id) is True


@pytest.mark.asyncio
async def test_non_party_sees_submitted_not_draft_on_public_case(db_session):
    filer = User(
        email="draft_filer@test.com", first_name="F", last_name="iler",
        user_type=UserType.ATTORNEY, bar_number="P999",
    )
    stranger = User(
        email="draft_stranger@test.com", first_name="S", last_name="ee",
        user_type=UserType.PUBLIC,
    )
    db_session.add_all([filer, stranger])
    court = Court(name="Draft Court", county="D", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()
    ct = CaseType(
        court_id=court.id, code="C", name="Civil",
        category=CaseCategory.CIVIL, filing_fee_cents=100,
    )
    db_session.add(ct)
    await db_session.flush()
    case = Case(
        court_id=court.id, case_number="DR-1", case_type_id=ct.id,
        title="X v Y", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
        is_sealed=False,
    )
    db_session.add(case)
    await db_session.flush()
    env_draft = FilingEnvelope(
        court_id=court.id, case_id=case.id, case_type_id=ct.id,
        filer_id=filer.id, status=FilingStatus.DRAFT,
    )
    env_sub = FilingEnvelope(
        court_id=court.id, case_id=case.id, case_type_id=ct.id,
        filer_id=filer.id, status=FilingStatus.SUBMITTED,
    )
    db_session.add_all([env_draft, env_sub])
    await db_session.flush()

    may_draft = await access_service.user_may_read_filing_envelope(
        db_session, stranger.id, env_draft
    )
    may_sub = await access_service.user_may_read_filing_envelope(
        db_session, stranger.id, env_sub
    )
    assert may_draft is False
    assert may_sub is True


@pytest.mark.asyncio
async def test_sealed_submitted_envelope_denied_to_stranger(db_session):
    filer = User(
        email="sef@test.com", first_name="F", last_name="iler",
        user_type=UserType.ATTORNEY, bar_number="P888",
    )
    stranger = User(
        email="ses@test.com", first_name="S", last_name="tr",
        user_type=UserType.PUBLIC,
    )
    db_session.add_all([filer, stranger])
    court = Court(name="Sealed Env Court", county="E", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()
    ct = CaseType(
        court_id=court.id, code="C", name="Civil",
        category=CaseCategory.CIVIL, filing_fee_cents=100,
    )
    db_session.add(ct)
    await db_session.flush()
    case = Case(
        court_id=court.id, case_number="SE-2", case_type_id=ct.id,
        title="Sealed", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
        is_sealed=True,
    )
    db_session.add(case)
    await db_session.flush()
    env = FilingEnvelope(
        court_id=court.id, case_id=case.id, case_type_id=ct.id,
        filer_id=filer.id, status=FilingStatus.SUBMITTED,
    )
    db_session.add(env)
    await db_session.flush()
    assert await access_service.user_may_read_filing_envelope(db_session, stranger.id, env) is False


@pytest.mark.asyncio
async def test_sealed_bar_on_party_row_does_not_grant_counsel_access(db_session):
    """Bar number on a non-attorney participant does not open a sealed case to that lawyer."""
    outsider = User(
        email="outside_bar@test.com", first_name="O", last_name="ut",
        user_type=UserType.ATTORNEY, bar_number="P777",
    )
    db_session.add(outsider)
    court = Court(name="Bar Party Court", county="B", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()
    ct = CaseType(
        court_id=court.id, code="C", name="Civil",
        category=CaseCategory.CIVIL, filing_fee_cents=100,
    )
    db_session.add(ct)
    await db_session.flush()
    case = Case(
        court_id=court.id, case_number="BP-1", case_type_id=ct.id,
        title="Sealed", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
        is_sealed=True,
    )
    db_session.add(case)
    await db_session.flush()
    db_session.add(CaseParticipant(
        case_id=case.id, role=ParticipantRole.DEFENDANT,
        party_name="Corp", attorney_bar_number="P777",
    ))
    await db_session.flush()
    assert await access_service.user_may_read_case(db_session, outsider.id, case.id) is False


@pytest.mark.asyncio
async def test_sealed_counsel_of_record_by_bar_and_role(db_session):
    """Counsel listed on attorney_* participant rows may access sealed cases."""
    counsel = User(
        email="on_file@test.com", first_name="C", last_name="ounsel",
        user_type=UserType.ATTORNEY, bar_number="P888",
    )
    db_session.add(counsel)
    court = Court(name="Counsel Court", county="C", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()
    ct = CaseType(
        court_id=court.id, code="C", name="Civil",
        category=CaseCategory.CIVIL, filing_fee_cents=100,
    )
    db_session.add(ct)
    await db_session.flush()
    case = Case(
        court_id=court.id, case_number="OC-1", case_type_id=ct.id,
        title="Sealed", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
        is_sealed=True,
    )
    db_session.add(case)
    await db_session.flush()
    db_session.add(CaseParticipant(
        case_id=case.id, role=ParticipantRole.ATTORNEY_DEFENDANT,
        party_name="Lawyer", attorney_bar_number="P888",
    ))
    await db_session.flush()
    assert await access_service.user_may_read_case(db_session, counsel.id, case.id) is True
