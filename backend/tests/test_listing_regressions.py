"""Listing behavior with enough records to expose pagination and query growth bugs."""

from datetime import UTC, datetime

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from app.api.auth import get_current_user_id, get_optional_user
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
    async def actor_account(db=Depends(get_db, scope="function")):
        return await db.get(User, user_id) if user_id is not None else None

    app.dependency_overrides[get_optional_user] = actor_account
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
    assert await access_service.user_may_read_case(db_session, owner, case.id) is (
        grant != "accepted_filings"
    )


@pytest.mark.parametrize("literal", ["%", "_", "\\", "/"])
async def test_case_search_treats_wildcards_as_literal_text(db_session, docket, literal):
    _, _, _, court, case, _ = docket
    case.case_number = f"LITERAL{literal}CASE"
    distractor = Case(court_id=court.id, case_type_id=case.case_type_id,
                      case_number="DISTRACTOR", title="Unrelated", filed_date=case.filed_date)
    db_session.add(distractor)
    await db_session.flush()
    db_session.add_all([
        CaseParticipant(case_id=case.id, role=ParticipantRole.PLAINTIFF,
                        party_name=f"Party{literal}Name"),
        # An unescaped % or _ would match this name too.
        CaseParticipant(case_id=distractor.id, role=ParticipantRole.PLAINTIFF,
                        party_name="Unrelated Party"),
    ])
    await db_session.flush()
    for params in [{"case_number": literal}, {"party_name": literal}]:
        cases, total = await search_service.search_cases(db_session, **params)
        assert total == 1
        assert [match.id for match in cases] == [case.id]


async def test_public_copy_docket_loads_only_page_copies_in_one_query(
    db_session, docket, api_client,
):
    from sqlalchemy import select

    from app.models.document_public_copy import DocumentPublicCopy

    owner, _, clerk, _, case, _ = docket
    case_id = case.id
    docs = list(await db_session.scalars(select(FilingDocument)))
    for doc in docs:
        copy = DocumentPublicCopy(
            document_id=doc.id, created_by=clerk.id, title=f"Public {doc.id}",
            file_key=f"copies/{doc.id}.pdf", mime_type="application/pdf", file_size_bytes=10,
            sha256_hash="a" * 64, page_count=1, is_text_searchable=True, pii_warnings=[],
        )
        db_session.add(copy)
        await db_session.flush()
        doc.public_copy_id = copy.id
        doc.is_confidential = True
    await db_session.flush()
    app.dependency_overrides[get_optional_user] = lambda: None
    queries, loaded = [], []

    def query(_conn, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    def load(_session, instance):
        if isinstance(instance, DocumentPublicCopy):
            loaded.append(instance.id)

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", query)
    event.listen(db_session.sync_session, "loaded_as_persistent", load)
    try:
        for size in [3, 25]:
            db_session.expunge_all()
            queries.clear()
            loaded.clear()
            response = await api_client.get(f"/api/v1/cases/{case_id}/filings?page_size={size}")
            assert response.status_code == 200
            documents = [doc for entry in response.json() for doc in entry["documents"]]
            assert len(documents) == size and len(loaded) == size
            assert all(doc["copy_id"] and doc["title"].startswith("Public ") for doc in documents)
            assert len(queries) <= 7, f"Docket grew to {len(queries)} queries for {size} copies"
            assert sum("FROM document_public_copies" in sql for sql in queries) == 1
    finally:
        event.remove(engine, "before_cursor_execute", query)
        event.remove(db_session.sync_session, "loaded_as_persistent", load)
        app.dependency_overrides.pop(get_optional_user, None)


@pytest.mark.parametrize("view", ["mine", "clerk", "waivers"])
async def test_summary_counts_current_attachments_without_loading_details(
    db_session, docket, api_client, view,
):
    owner, _, clerk, court, _, envelopes = docket
    filing = next(row for row in reversed(envelopes) if row.filer_id == owner.id)
    filing.status = FilingStatus.SUBMITTED
    filing.submitted_at = datetime.now(UTC)
    filing.fee_waiver_requested = True
    filing.fee_waiver_reason = "Private application explanation"
    filing.filing_date_basis = {"private": "Date evidence"}
    for code, removed in [
        ("FEE_WAIVER", False), ("EXHIBIT", True),
        ("FEE_WAIVER_ORDER", False), ("FILING_DATE_ORDER", False),
    ]:
        db_session.add(FilingDocument(
            envelope_id=filing.id, document_type_code=code, title=code,
            file_key=f"summary/{code}", file_size_bytes=1, mime_type="text/plain",
            sha256_hash="0" * 64, removed_at=datetime.now(UTC) if removed else None,
        ))
    await db_session.flush()
    fid, actor_id, court_id = filing.id, owner.id if view == "mine" else clerk.id, court.id
    db_session.expunge_all()
    app.dependency_overrides[get_current_user_id] = lambda: actor_id
    loaded, selects = [], []

    def record_loaded(_session, instance):
        loaded.append(type(instance))

    def record_query(_conn, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record_query)
    event.listen(db_session.sync_session, "loaded_as_persistent", record_loaded)
    try:
        path = (
            "/api/v1/filings?status=submitted" if view == "mine"
            else f"/api/v1/clerk/queue?court_id={court_id}&fee_waivers={view == 'waivers'}"
        )
        response = await api_client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        summary = body["filings"][0]
        assert summary["id"] == fid
        assert summary["document_count"] == 2
        assert not {"documents", "fee_waiver_reason", "filing_date_basis"} & summary.keys()
        assert FilingDocument not in loaded and FilingEnvelope not in loaded
        assert len(selects) <= 3
        # Opening the same filing still supplies its full, authorized current record.
        detail = await api_client.get(f"/api/v1/filings/{fid}")
        assert detail.status_code == 200
        assert len(detail.json()["documents"]) == summary["document_count"]
        assert detail.json()["fee_waiver_reason"] == "Private application explanation"
    finally:
        event.remove(engine, "before_cursor_execute", record_query)
        event.remove(db_session.sync_session, "loaded_as_persistent", record_loaded)
        app.dependency_overrides.pop(get_current_user_id, None)


async def test_a_party_opening_a_docket_loads_the_account_and_case_access_once(
    db_session, api_client, docket,
):
    owner, _, _, _, case, _ = docket
    db_session.add(CaseParticipant(
        case_id=case.id, user_id=owner.id, role=ParticipantRole.PLAINTIFF, party_name="Owner",
        access_enabled=True, reviewed_at=datetime.now(UTC),
    ))
    await db_session.flush()
    case_id, owner_id = case.id, owner.id
    db_session.expunge_all()
    selects = []

    def record_query(_conn, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(" ".join(statement.split()))

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record_query)
    try:
        response = await api_client.get(
            f"/api/v1/cases/{case_id}", headers={"X-Demo-User-Id": str(owner_id)},
        )
    finally:
        event.remove(engine, "before_cursor_execute", record_query)
    assert response.status_code == 200, response.text
    assert response.json()["can_file"] is True
    assert sum(sql.startswith("SELECT users.") for sql in selects) == 1, selects
    assert sum(sql.startswith("SELECT cases.id FROM cases") for sql in selects) == 1, selects
