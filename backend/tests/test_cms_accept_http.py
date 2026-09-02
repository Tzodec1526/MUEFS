"""CMS failure must persist on the envelope after the HTTP 502 (get_db commits)."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.integrations.cms_adapter import CMSFilingResult
from app.main import app
from app.models.court import CaseCategory, CaseType, Court, CourtType
from app.models.filing import FilingDocument, FilingEnvelope, FilingStatus
from app.models.user import CourtRole, User, UserCourtRole, UserType
from app.services import filing_service


@pytest_asyncio.fixture
async def cms_fail_app(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    class FailingAdapter:
        async def submit_filing(self, **_kwargs):
            return CMSFilingResult(success=False, error_message="JIS unavailable")

    monkeypatch.setattr(
        "app.services.filing_service.get_cms_adapter",
        lambda _cms_type: FailingAdapter(),
    )

    ids: dict[str, int] = {}
    async with factory() as s:
        filer = User(
            email="cms_filer@test.com", first_name="F", last_name="iler",
            user_type=UserType.ATTORNEY, bar_number="P20202",
        )
        clerk = User(
            email="cms_clerk@test.com", first_name="C", last_name="lerk",
            user_type=UserType.CLERK,
        )
        s.add_all([filer, clerk])
        court = Court(name="CMS Fail Court", county="Wayne", court_type=CourtType.CIRCUIT)
        s.add(court)
        await s.flush()
        s.add(UserCourtRole(user_id=clerk.id, court_id=court.id, role=CourtRole.CLERK))
        ct = CaseType(
            court_id=court.id, code="CIV", name="Civil",
            category=CaseCategory.CIVIL, filing_fee_cents=15000,
        )
        s.add(ct)
        await s.flush()
        env = FilingEnvelope(
            court_id=court.id, case_type_id=ct.id, filer_id=filer.id,
            status=FilingStatus.DRAFT, case_title="CMS HTTP",
        )
        s.add(env)
        await s.flush()
        s.add(FilingDocument(
            envelope_id=env.id, document_type_code="COMPLAINT", title="Complaint",
            file_key="k", file_size_bytes=1, mime_type="application/pdf",
            sha256_hash="0" * 64, is_text_searchable=True,
        ))
        await s.flush()
        submitted = await filing_service.submit_filing(s, env.id)
        assert submitted is not None
        ids = {"filing": env.id, "clerk": clerk.id}
        await s.commit()

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
        yield client, ids, factory
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_cms_failure_persists_after_http_502(cms_fail_app):
    client, ids, factory = cms_fail_app
    r = await client.post(
        f"/api/v1/clerk/filings/{ids['filing']}/review",
        json={"action": "accept"},
        headers={"X-Demo-User-Id": str(ids["clerk"])},
    )
    assert r.status_code == 502
    assert "JIS unavailable" in r.text

    async with factory() as s:
        env = await s.get(FilingEnvelope, ids["filing"])
        assert env is not None
        assert env.status != FilingStatus.ACCEPTED
        assert env.cms_error == "JIS unavailable"
