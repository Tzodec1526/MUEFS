"""Listing behavior with enough records to expose pagination and query growth bugs."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from app.api.auth import get_current_user_id, get_optional_user_id
from app.database import get_db
from app.main import app
from app.models.case import Case, CaseParticipant, ParticipantRole
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import access_service, search_service


@pytest.fixture
async def docket(db_session):
    owner, stranger, clerk = [
        User(email=f"{name}@listing.test", first_name=name, last_name="User", user_type=kind)
        for name, kind in [("owner", UserType.ATTORNEY), ("stranger", UserType.ATTORNEY),
                           ("clerk", UserType.CLERK)]
    ]
    court = Court(name="Listing Court", county="Wayne", court_type=CourtType.CIRCUIT)
    db_session.add_all([owner, stranger, clerk, court])
    await db_session.flush()
    case_type = CaseType(court_id=court.id, code="CIV", name="Civil",
                         category=CaseCategory.CIVIL, filing_fee_cents=100)
    db_session.add(case_type)
    await db_session.flush()
    case = Case(court_id=court.id, case_type_id=case_type.id, case_number="LIST-1",
                title="Listing Case", filed_date=datetime.now(UTC))
    db_session.add(case)
    db_session.add(UserCourtRole(user_id=clerk.id, court_id=court.id, role=CourtRole.CLERK))
    await db_session.flush()
    envelopes = []
    for i in range(90):
        envelope = FilingEnvelope(
            court_id=court.id, case_type_id=case_type.id, case_id=case.id,
            filer_id=owner.id if i % 2 else stranger.id,
            status=[FilingStatus.DRAFT, FilingStatus.ACCEPTED, FilingStatus.RETURNED][i % 3],
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        db_session.add(envelope)
        envelopes.append(envelope)
    await db_session.flush()
    for envelope in envelopes:
        db_session.add(FilingDocument(
            envelope_id=envelope.id, document_type_code="EXHIBIT", title="Attachment",
            file_key=f"listing/{envelope.id}", file_size_bytes=1, mime_type="text/plain",
            sha256_hash="0" * 64,
        ))
    await db_session.flush()
    return owner, stranger, clerk, court, case, envelopes


@pytest.mark.parametrize("actor", ["anonymous", "owner", "clerk"])
async def test_docket_filters_before_paging_with_bounded_queries(db_session, docket, actor):
    owner, _, clerk, _, case, envelopes = docket
    user_id = {"anonymous": None, "owner": owner.id, "clerk": clerk.id}[actor]
    case_id = case.id
    expected = sorted([
        env.id for env in envelopes
        if actor == "clerk" or env.status == FilingStatus.ACCEPTED or env.filer_id == user_id
    ], reverse=True)
    db_session.expunge_all()

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_optional_user_id] = lambda: user_id
    selects = []
    loaded_filings = []

    def record_query(_conn, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    def record_loaded(_session, instance):
        if isinstance(instance, FilingEnvelope):
            loaded_filings.append(instance.id)

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record_query)
    event.listen(db_session.sync_session, "loaded_as_persistent", record_loaded)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/cases/{case_id}/filings?page=2&page_size=3")
        assert response.status_code == 200
        assert [env["id"] for env in response.json()] == expected[3:6]
        assert all(len(env["documents"]) == 1 for env in response.json())
        assert len(selects) <= 6, f"Docket issued {len(selects)} SELECTs for one page"
        assert len(loaded_filings) == 3, "Off-page envelopes were materialized"
    finally:
        event.remove(engine, "before_cursor_execute", record_query)
        event.remove(db_session.sync_session, "loaded_as_persistent", record_loaded)
        app.dependency_overrides.clear()


async def test_filing_counts_cover_all_pages_and_filters_without_other_users(db_session, docket):
    owner, _, _, court, _, _ = docket

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_id] = lambda: owner.id
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/filings?status=returned&page=2&page_size=4")
            summary = await client.get("/api/v1/filings/summary")
        assert response.status_code == summary.status_code == 200
        body = response.json()
        assert body["total"] == 15
        assert len(body["filings"]) == 4
        assert all(env["status"] == "returned" for env in body["filings"])
        assert body["court_names"] == {str(court.id): court.name}
        assert body["status_counts"] == summary.json()
        assert sum(body["status_counts"].values()) == 45
        assert body["status_counts"]["draft"] == 15
        assert body["status_counts"]["served"] == 0
    finally:
        app.dependency_overrides.clear()


async def test_clerk_queue_applies_status_filter_and_pagination(db_session, docket):
    _, _, clerk, court, _, envelopes = docket
    for i, envelope in enumerate(envelopes):
        envelope.status = FilingStatus.SUBMITTED if i % 2 else FilingStatus.UNDER_REVIEW
    db_session.add(UserCourtRole(user_id=clerk.id, court_id=court.id, role=CourtRole.ADMIN))
    await db_session.flush()

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_id] = lambda: clerk.id
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/clerk/queue?court_id={court.id}&status=under_review&page=2"
            )
            invalid = await client.get(f"/api/v1/clerk/queue?court_id={court.id}&status=draft")
        assert response.status_code == 200
        assert response.json()["total"] == 45
        assert len(response.json()["filings"]) == 20
        assert all(row["status"] == "under_review" for row in response.json()["filings"])
        assert invalid.status_code == 400
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("grant", ["participant", "accepted_filings", "court_roles"])
async def test_sealed_access_uses_explicit_grants_not_accepted_filings(db_session, docket, grant):
    owner, _, _, court, case, _ = docket
    case.is_sealed = True
    if grant == "participant":
        db_session.add_all([
            CaseParticipant(case_id=case.id, user_id=owner.id, role=role, party_name="Owner",
                            access_enabled=True)
            for role in [ParticipantRole.PLAINTIFF, ParticipantRole.PETITIONER]
        ])
    elif grant == "court_roles":
        db_session.add_all([
            UserCourtRole(user_id=owner.id, court_id=court.id, role=role)
            for role in [CourtRole.CLERK, CourtRole.ADMIN]
        ])
    await db_session.flush()
    assert await access_service.user_may_read_case(db_session, owner.id, case.id) is (
        grant != "accepted_filings"
    )


@pytest.mark.parametrize("literal", ["%", "_", "\\", "/"])
async def test_case_search_treats_wildcards_as_literal_text(db_session, docket, literal):
    _, _, _, court, case, _ = docket
    case.case_number = f"LITERAL{literal}CASE"
    db_session.add_all([
        CaseParticipant(case_id=case.id, role=ParticipantRole.PLAINTIFF,
                        party_name=f"Party{literal}Name"),
        Case(court_id=court.id, case_type_id=case.case_type_id, case_number="DISTRACTOR",
             title="Unrelated", filed_date=case.filed_date),
    ])
    await db_session.flush()
    for params in [{"case_number": literal}, {"party_name": literal}]:
        cases, total = await search_service.search_cases(db_session, **params)
        assert total == 1
        assert [match.id for match in cases] == [case.id]
