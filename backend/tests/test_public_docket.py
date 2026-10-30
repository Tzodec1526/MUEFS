"""End-to-end: the public docket is reachable WITHOUT an account.

Exercises the real FastAPI app over HTTP with no Authorization or X-Demo-User-Id header,
proving an anonymous visitor can search the index and open a non-sealed docket, while sealed
matters and confidential documents stay locked. Uses a shared in-memory SQLite database
(StaticPool) wired in through a get_db dependency override.
"""

from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.case import Case, CaseParticipant, CaseStatus, ParticipantRole
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.user import User, UserType


@pytest_asyncio.fixture
async def public_app():
    """App wired to a seeded, shared in-memory DB; yields (client, ids) with no auth."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    ids: dict[str, int] = {}
    async with factory() as s:
        filer = User(
            email="pub_filer@test.com", first_name="F", last_name="iler",
            user_type=UserType.ATTORNEY, bar_number="P10101",
        )
        s.add(filer)
        court = Court(name="Public Docket Court", county="Wayne", court_type=CourtType.CIRCUIT)
        s.add(court)
        await s.flush()
        ct = CaseType(
            court_id=court.id, code="CIV", name="Civil",
            category=CaseCategory.CIVIL, filing_fee_cents=15000,
        )
        s.add(ct)
        await s.flush()

        open_case = Case(
            court_id=court.id, case_number="MI-PUB-OPEN-1", case_type_id=ct.id,
            title="Public v Records", status=CaseStatus.OPEN,
            filed_date=datetime.now(UTC), is_sealed=False,
        )
        sealed_case = Case(
            court_id=court.id, case_number="MI-PUB-SEAL-1", case_type_id=ct.id,
            title="Sealed v Hidden", status=CaseStatus.OPEN,
            filed_date=datetime.now(UTC), is_sealed=True,
        )
        s.add_all([open_case, sealed_case])
        await s.flush()

        closed_intake = Court(name="Retained Records Court", county="Alcona",
                              court_type=CourtType.CIRCUIT, is_efiling_enabled=False)
        s.add(closed_intake)
        await s.flush()
        other_type = CaseType(court_id=closed_intake.id, code="CIV", name="Civil",
                              category=CaseCategory.CIVIL, filing_fee_cents=0)
        s.add(other_type)
        await s.flush()
        same_number = Case(court_id=closed_intake.id, case_type_id=other_type.id,
                           case_number=open_case.case_number, title="Another public matter",
                           status=CaseStatus.OPEN, filed_date=datetime.now(UTC))
        s.add(same_number)
        await s.flush()

        # Litigant with contact PII — must NOT surface on the public docket.
        s.add(CaseParticipant(
            case_id=open_case.id, role=ParticipantRole.PLAINTIFF,
            party_name="Jane Public",
            contact_email="jane@example.com",
            contact_phone="555-0100",
            contact_address="123 Main St, Detroit MI",
        ))
        await s.flush()

        env = FilingEnvelope(
            court_id=court.id, case_id=open_case.id, case_type_id=ct.id,
            filer_id=filer.id, status=FilingStatus.ACCEPTED,
        )
        s.add(env)
        await s.flush()
        public_doc = FilingDocument(
            envelope_id=env.id, document_type_code="COMPLAINT", title="Complaint",
            file_key="k_public", file_size_bytes=1, mime_type="application/pdf",
            sha256_hash="0" * 64, is_confidential=False,
        )
        confidential_doc = FilingDocument(
            envelope_id=env.id, document_type_code="EXHIBIT", title="Sealed Exhibit",
            file_key="k_conf", file_size_bytes=1, mime_type="application/pdf",
            sha256_hash="1" * 64, is_confidential=True,
        )
        s.add_all([public_doc, confidential_doc])
        await s.flush()
        await s.commit()

        ids = {
            "open_case": open_case.id,
            "sealed_case": sealed_case.id,
            "public_doc": public_doc.id,
            "confidential_doc": confidential_doc.id,
            "court": court.id,
            "closed_intake": closed_intake.id,
            "same_number": same_number.id,
        }

    async def _override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, ids
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_anonymous_search_returns_open_not_sealed(public_app):
    client, ids = public_app
    r = await client.get("/api/v1/cases/search")  # no auth headers
    assert r.status_code == 200
    body = r.json()
    numbers = {c["case_number"] for c in body["cases"]}
    assert "MI-PUB-OPEN-1" in numbers
    assert "MI-PUB-SEAL-1" not in numbers
    assert all(c["filed_date"].endswith("Z") for c in body["cases"])


async def test_anonymous_search_distinguishes_courts_without_exposing_contacts(public_app):
    client, ids = public_app
    response = await client.get("/api/v1/cases/search", params={"case_number": "MI-PUB-OPEN-1"})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2
    cases = {case["id"]: case for case in response.json()["cases"]}
    assert cases[ids["open_case"]]["court_name"] == "Public Docket Court"
    assert cases[ids["open_case"]]["court_county"] == "Wayne"
    assert cases[ids["same_number"]]["court_name"] == "Retained Records Court"
    assert cases[ids["same_number"]]["court_county"] == "Alcona"
    assert cases[ids["open_case"]]["participants"][0]["party_name"] == "Jane Public"
    assert "contact_" not in response.text
    for court, case in [("court", "open_case"), ("closed_intake", "same_number")]:
        filtered = await client.get("/api/v1/cases/search", params={
            "case_number": "MI-PUB-OPEN-1", "court_id": ids[court],
        })
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["total"] == 1
        assert [item["id"] for item in filtered.json()["cases"]] == [ids[case]]
    sealed = await client.get("/api/v1/cases/search", params={
        "case_number": "MI-PUB-SEAL-1", "court_id": ids["court"],
    })
    assert sealed.json()["total"] == 0
    assert sealed.json()["cases"] == []
    invalid = await client.get("/api/v1/cases/search", params={"court_id": 2**31})
    assert invalid.status_code == 422  # Reject IDs that PostgreSQL cannot represent.


@pytest.mark.asyncio
async def test_anonymous_opens_non_sealed_docket(public_app):
    client, ids = public_app
    r = await client.get(f"/api/v1/cases/{ids['open_case']}")
    assert r.status_code == 200
    assert r.json()["case_number"] == "MI-PUB-OPEN-1"
    assert r.json()["filed_date"].endswith("Z")


@pytest.mark.asyncio
async def test_public_docket_strips_participant_contact_pii(public_app):
    """The open docket shows party names but never litigant contact details."""
    client, ids = public_app
    r = await client.get(f"/api/v1/cases/{ids['open_case']}")
    assert r.status_code == 200
    participants = r.json()["participants"]
    assert any(p["party_name"] == "Jane Public" for p in participants)
    for p in participants:
        assert "contact_email" not in p
        assert "contact_phone" not in p
        assert "contact_address" not in p


@pytest.mark.asyncio
async def test_anonymous_blocked_from_sealed_docket(public_app):
    client, ids = public_app
    r = await client.get(f"/api/v1/cases/{ids['sealed_case']}")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_anonymous_lists_public_case_filings(public_app):
    client, ids = public_app
    r = await client.get(f"/api/v1/cases/{ids['open_case']}/filings")
    assert r.status_code == 200
    assert len(r.json()) == 1  # the accepted envelope


@pytest.mark.asyncio
async def test_anonymous_blocked_from_confidential_document(public_app):
    client, ids = public_app
    # Access is denied before any storage read, so a 403 (not 404/500) is the contract.
    r = await client.get(f"/api/v1/documents/{ids['confidential_doc']}/download")
    assert r.status_code == 403


async def test_docket_lists_filings_newest_first_by_filing_date(db_session, api_client):
    filer = User(email="order@test.com", first_name="Order", last_name="Filer",
                 user_type=UserType.ATTORNEY)
    court = Court(name="Order Court", county="Wayne", court_type=CourtType.CIRCUIT)
    db_session.add_all([filer, court])
    await db_session.flush()
    kind = CaseType(court_id=court.id, code="CIV", name="Civil", category=CaseCategory.CIVIL)
    db_session.add(kind)
    await db_session.flush()
    case = Case(court_id=court.id, case_type_id=kind.id, case_number="ORDER-1",
                title="Order v Docket", filed_date=datetime.now(UTC))
    db_session.add(case)
    await db_session.flush()
    # Drafted first, filed last: the draft's age says nothing about docket order.
    later, earlier = (
        FilingEnvelope(court_id=court.id, case_id=case.id, case_type_id=kind.id,
                       filer_id=filer.id, status=FilingStatus.ACCEPTED,
                       filing_date=filed)
        for filed in (date(2026, 9, 10), date(2026, 9, 5))
    )
    db_session.add(later)
    await db_session.flush()
    db_session.add(earlier)
    await db_session.flush()
    listed = await api_client.get(f"/api/v1/cases/{case.id}/filings")
    assert [f["id"] for f in listed.json()] == [later.id, earlier.id]
    # A missing case is not reported as sealed.
    assert (await api_client.get("/api/v1/cases/987654/filings")).status_code == 404
