from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.case import Case
from app.models.court import CaseCategory, CaseType, Court, CourtType, FilingRequirement
from app.models.filing import FilingEnvelope, FilingStatus
from app.models.user import User, UserType


@pytest_asyncio.fixture
async def stats_app():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as s:
        s.add(
            Court(
                name="Stats Court",
                county="Wayne",
                court_type=CourtType.CIRCUIT,
                is_efiling_enabled=True,
            )
        )
        await s.commit()

    async def override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_public_stats_no_auth(stats_app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/public/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["courts_efiling_enabled"] >= 1
    assert "public_cases_indexed" in body
    assert "total_filings" in body
    assert body["max_upload_mb"] == 100
    assert body["mifile_max_upload_mb"] == 25
    assert body["cms_integration"] == "stub"


async def test_public_stats_count_everything_in_one_statement(db_session, api_client):
    open_court = Court(name="Open", county="Wayne", court_type=CourtType.CIRCUIT,
                       is_efiling_enabled=True)
    closed_court = Court(name="Closed", county="Kent", court_type=CourtType.CIRCUIT,
                         is_efiling_enabled=False)
    filer = User(email="stats@example.com", first_name="Stats", last_name="Filer",
                 user_type=UserType.ATTORNEY)
    db_session.add_all([open_court, closed_court, filer])
    await db_session.flush()
    kinds = [
        CaseType(court_id=court.id, code="C", name="Civil", category=CaseCategory.CIVIL,
                 filing_fee_cents=0)
        for court in (open_court, closed_court)
    ]
    db_session.add_all(kinds)
    await db_session.flush()
    db_session.add_all([
        Case(court_id=open_court.id, case_number=f"STATS-{number}", case_type_id=kinds[0].id,
             title="Stats matter", filed_date=datetime.now(UTC), is_sealed=sealed)
        for number, sealed in enumerate([False, False, True])
    ])
    db_session.add_all([
        FilingEnvelope(court_id=open_court.id, case_type_id=kinds[0].id, filer_id=filer.id,
                       filing_type="initial", status=status)
        for status in [FilingStatus.DRAFT, FilingStatus.SUBMITTED, FilingStatus.UNDER_REVIEW,
                       FilingStatus.ACCEPTED, FilingStatus.RETURNED]
    ])
    db_session.add_all([
        FilingRequirement(court_id=kind.court_id, case_type_id=kind.id,
                          document_type_code=code, description=code)
        for kind in kinds for code in ["COMPLAINT", "SUMMONS"]
    ] + [FilingRequirement(court_id=open_court.id, case_type_id=kinds[0].id,
                           document_type_code="EXHIBIT", description="Exhibit")])
    await db_session.flush()
    selects = []

    def record(_conn, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        response = await api_client.get("/api/v1/public/stats")
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "courts_efiling_enabled": 1,
        "public_cases_indexed": 2,
        "total_filings": 5,
        "pending_clerk_review": 2,
        "mcr_document_types": 3,
        "max_upload_mb": settings.max_file_size_mb,
        "mifile_max_upload_mb": 25,
        "cms_integration": "stub",
    }
    assert len(selects) == 1, selects
