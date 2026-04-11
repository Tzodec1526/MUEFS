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
    assert await access_service.user_may_read_case(db_session, other.id, case.id) is False


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
