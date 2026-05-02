"""Liveness vs readiness endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_is_liveness_only() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_passes_when_db_reachable() -> None:
    """The default settings point at a Postgres URL that isn't running in CI; ``get_db``
    will raise on first use. We simulate the success path by overriding the dependency.
    """
    from app.database import get_db

    class _FakeSession:
        async def execute(self, *_args, **_kwargs):
            return None

    async def _ok():
        yield _FakeSession()

    app.dependency_overrides[get_db] = _ok
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/health/ready")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ready"
        assert body["checks"]["database"] == "ok"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_readiness_fails_when_db_errors() -> None:
    from app.database import get_db

    class _BrokenSession:
        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("db is down")

    async def _broken():
        yield _BrokenSession()

    app.dependency_overrides[get_db] = _broken
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/health/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "unready"
        assert body["reason"] == "database"
    finally:
        app.dependency_overrides.pop(get_db, None)
