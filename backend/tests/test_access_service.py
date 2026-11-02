from datetime import UTC, datetime

import pytest

from app.models.case import Case, CaseParticipant, CaseStatus, ParticipantRole
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import access_service


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
        title="X v Y", status=CaseStatus.OPEN, filed_date=datetime.now(UTC), is_sealed=True,
    )
    db_session.add(case)
    await db_session.flush()

    assert await access_service.user_may_read_case(db_session, None, case.id) is False
    assert await access_service.user_may_read_case(db_session, clerk, case.id) is True


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

    assert await access_service.user_may_read_document(db_session, filer, doc) is True
    assert await access_service.user_may_read_document(db_session, stranger, doc) is False


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
        party_name="Party Person", access_enabled=True,
    ))
    await db_session.flush()

    assert await access_service.user_may_read_case(db_session, party, case.id) is True
    assert await access_service.user_may_read_case(db_session, stranger, case.id) is False


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
    assert await access_service.user_may_read_case(db_session, viewer, case.id) is True


@pytest.mark.asyncio
async def test_non_party_sees_accepted_not_pending_on_public_case(db_session):
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
        db_session, stranger, env_draft
    )
    may_sub = await access_service.user_may_read_filing_envelope(
        db_session, stranger, env_sub
    )
    assert may_draft is False
    assert may_sub is False

    env_acc = FilingEnvelope(
        court_id=court.id, case_id=case.id, case_type_id=ct.id,
        filer_id=filer.id, status=FilingStatus.ACCEPTED,
    )
    db_session.add(env_acc)
    await db_session.flush()
    may_acc = await access_service.user_may_read_filing_envelope(
        db_session, stranger, env_acc
    )
    assert may_acc is True


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
    assert await access_service.user_may_read_filing_envelope(db_session, stranger, env) is False


@pytest.mark.asyncio
async def test_sealed_counsel_requires_an_explicit_link_and_current_bar_verification(db_session):
    counsel = User(
        email="counsel@test.com", first_name="Court", last_name="Counsel",
        user_type=UserType.ATTORNEY, bar_number="P888", bar_number_verified=True,
    )
    db_session.add(counsel)
    court, case_type = await _court_and_case_type(db_session)
    case = Case(
        court_id=court.id, case_type_id=case_type.id, case_number="COUNSEL-1",
        title="Sealed", filed_date=datetime.now(UTC), is_sealed=True,
    )
    db_session.add(case)
    await db_session.flush()
    record = CaseParticipant(
        case_id=case.id, role=ParticipantRole.ATTORNEY_DEFENDANT,
        party_name="Counsel", attorney_bar_number="P888", access_enabled=True,
    )
    db_session.add(record)
    await db_session.flush()
    assert not await access_service.user_may_read_case(db_session, counsel, case.id)
    record.user_id = counsel.id
    await db_session.flush()
    assert await access_service.user_may_read_case(db_session, counsel, case.id)
    counsel.bar_number_verified = False
    await db_session.flush()
    assert not await access_service.user_may_read_case(db_session, counsel, case.id)
    counsel.bar_number_verified = True
    counsel.bar_number = "P999"
    await db_session.flush()
    assert not await access_service.user_may_read_case(db_session, counsel, case.id)
    counsel.bar_number = "P888"
    record.is_active = False
    await db_session.flush()
    assert not await access_service.user_may_read_case(db_session, counsel, case.id)



async def _court_and_case_type(db_session):
    court = Court(name="Anon Court", county="A", court_type=CourtType.CIRCUIT)
    db_session.add(court)
    await db_session.flush()
    ct = CaseType(
        court_id=court.id, code="C", name="Civil",
        category=CaseCategory.CIVIL, filing_fee_cents=100,
    )
    db_session.add(ct)
    await db_session.flush()
    return court, ct


@pytest.mark.asyncio
async def test_anonymous_reads_non_sealed_case_but_not_sealed(db_session):
    court, ct = await _court_and_case_type(db_session)
    open_case = Case(
        court_id=court.id, case_number="ANON-OPEN", case_type_id=ct.id,
        title="Open matter", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
        is_sealed=False,
    )
    sealed_case = Case(
        court_id=court.id, case_number="ANON-SEAL", case_type_id=ct.id,
        title="Sealed matter", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
        is_sealed=True,
    )
    db_session.add_all([open_case, sealed_case])
    await db_session.flush()

    assert await access_service.user_may_read_case(db_session, None, open_case.id) is True
    assert await access_service.user_may_read_case(db_session, None, sealed_case.id) is False


@pytest.mark.asyncio
async def test_anonymous_document_access_public_yes_confidential_no(db_session):
    court, ct = await _court_and_case_type(db_session)
    filer = User(
        email="anon_doc_filer@test.com", first_name="F", last_name="iler",
        user_type=UserType.ATTORNEY, bar_number="P123",
    )
    db_session.add(filer)
    case = Case(
        court_id=court.id, case_number="ANON-DOC", case_type_id=ct.id,
        title="Open", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
        is_sealed=False,
    )
    db_session.add(case)
    await db_session.flush()
    env = FilingEnvelope(
        court_id=court.id, case_id=case.id, case_type_id=ct.id,
        filer_id=filer.id, status=FilingStatus.ACCEPTED,
    )
    db_session.add(env)
    await db_session.flush()
    public_doc = FilingDocument(
        envelope_id=env.id, document_type_code="COMPLAINT", title="Public",
        file_key="k1", file_size_bytes=1, mime_type="application/pdf",
        sha256_hash="0" * 64, is_confidential=False,
    )
    confidential_doc = FilingDocument(
        envelope_id=env.id, document_type_code="EXHIBIT", title="Confidential",
        file_key="k2", file_size_bytes=1, mime_type="application/pdf",
        sha256_hash="1" * 64, is_confidential=True,
    )
    db_session.add_all([public_doc, confidential_doc])
    await db_session.flush()

    may_public = await access_service.user_may_read_document(db_session, None, public_doc)
    may_conf = await access_service.user_may_read_document(db_session, None, confidential_doc)
    assert may_public is True
    assert may_conf is False


@pytest.mark.asyncio
async def test_anonymous_sees_accepted_envelope_not_draft(db_session):
    court, ct = await _court_and_case_type(db_session)
    filer = User(
        email="anon_env_filer@test.com", first_name="F", last_name="iler",
        user_type=UserType.ATTORNEY, bar_number="P456",
    )
    db_session.add(filer)
    case = Case(
        court_id=court.id, case_number="ANON-ENV", case_type_id=ct.id,
        title="Open", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
        is_sealed=False,
    )
    db_session.add(case)
    await db_session.flush()
    env_draft = FilingEnvelope(
        court_id=court.id, case_id=case.id, case_type_id=ct.id,
        filer_id=filer.id, status=FilingStatus.DRAFT,
    )
    env_accepted = FilingEnvelope(
        court_id=court.id, case_id=case.id, case_type_id=ct.id,
        filer_id=filer.id, status=FilingStatus.ACCEPTED,
    )
    db_session.add_all([env_draft, env_accepted])
    await db_session.flush()

    may_draft = await access_service.user_may_read_filing_envelope(db_session, None, env_draft)
    may_acc = await access_service.user_may_read_filing_envelope(db_session, None, env_accepted)
    assert may_draft is False
    assert may_acc is True


@pytest.mark.asyncio
async def test_anonymous_does_not_see_rejected_returned_or_served(db_session):
    court, ct = await _court_and_case_type(db_session)
    filer = User(
        email="anon_hidden_filer@test.com", first_name="F", last_name="iler",
        user_type=UserType.ATTORNEY, bar_number="P457",
    )
    db_session.add(filer)
    case = Case(
        court_id=court.id, case_number="ANON-HIDE", case_type_id=ct.id,
        title="Open", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
        is_sealed=False,
    )
    db_session.add(case)
    await db_session.flush()
    hidden = []
    for st in (FilingStatus.REJECTED, FilingStatus.RETURNED, FilingStatus.SERVED,
               FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW):
        env = FilingEnvelope(
            court_id=court.id, case_id=case.id, case_type_id=ct.id,
            filer_id=filer.id, status=st,
        )
        db_session.add(env)
        hidden.append(env)
    await db_session.flush()
    for env in hidden:
        assert await access_service.user_may_read_filing_envelope(
            db_session, None, env
        ) is False


@pytest.mark.asyncio
async def test_sealed_draft_does_not_grant_stranger_case_access(db_session):
    filer = User(
        email="seal_draft_filer@test.com", first_name="F", last_name="iler",
        user_type=UserType.ATTORNEY, bar_number="P321",
    )
    stranger = User(
        email="seal_draft_stranger@test.com", first_name="S", last_name="tr",
        user_type=UserType.ATTORNEY, bar_number="P322",
    )
    db_session.add_all([filer, stranger])
    court, ct = await _court_and_case_type(db_session)
    case = Case(
        court_id=court.id, case_number="SEAL-DRAFT", case_type_id=ct.id,
        title="Sealed", status=CaseStatus.OPEN, filed_date=datetime.now(UTC),
        is_sealed=True,
    )
    db_session.add(case)
    await db_session.flush()
    db_session.add(FilingEnvelope(
        court_id=court.id, case_id=case.id, case_type_id=ct.id,
        filer_id=stranger.id, status=FilingStatus.DRAFT,
    ))
    await db_session.flush()
    assert await access_service.user_may_read_case(db_session, stranger, case.id) is False
