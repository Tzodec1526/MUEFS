"""Public platform stats endpoint."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.court import Court, CourtType


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
