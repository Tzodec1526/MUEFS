"""End-to-end: the public docket is reachable WITHOUT an account.

Exercises the real FastAPI app over HTTP with no Authorization or X-Demo-User-Id header,
proving an anonymous visitor can search the index and open a non-sealed docket, while sealed
matters and confidential documents stay locked. Uses a shared in-memory SQLite database
(StaticPool) wired in through a get_db dependency override.
"""

from datetime import UTC, datetime

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


@pytest.mark.asyncio
async def test_anonymous_opens_non_sealed_docket(public_app):
    client, ids = public_app
    r = await client.get(f"/api/v1/cases/{ids['open_case']}")
    assert r.status_code == 200
    assert r.json()["case_number"] == "MI-PUB-OPEN-1"


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


@pytest.mark.asyncio
async def test_download_simulated_document_is_friendly_not_500(public_app):
    """A seeded/demo document has a DB record but no stored file. Downloading it must
    return a clear 'simulated document' message, never a raw 500."""
    client, ids = public_app
    r = await client.get(f"/api/v1/documents/{ids['public_doc']}/download")
    assert r.status_code == 404
    assert "Simulated document" in r.text
    assert "Internal server error" not in r.text
