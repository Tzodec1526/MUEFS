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


def _override_readiness_session(session_obj):
    """Install a fake session-yielding dependency for the readiness probe."""
    from app.main import _readiness_db_session

    async def _gen():
        yield session_obj

    app.dependency_overrides[_readiness_db_session] = _gen
    return _readiness_db_session


@pytest.mark.asyncio
async def test_readiness_passes_when_db_reachable() -> None:
    """The default settings point at a Postgres URL that isn't running in CI; the
    readiness session would raise on first use. We simulate the success path by
    overriding the dependency.
    """

    class _FakeSession:
        async def execute(self, *_args, **_kwargs):
            return None

    dep = _override_readiness_session(_FakeSession())
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/health/ready")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ready"
        assert body["checks"]["database"] == "ok"
    finally:
        app.dependency_overrides.pop(dep, None)


@pytest.mark.asyncio
async def test_readiness_fails_when_db_errors() -> None:
    class _BrokenSession:
        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("db is down")

    dep = _override_readiness_session(_BrokenSession())
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/health/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "unready"
        assert body["reason"] == "database"
    finally:
        app.dependency_overrides.pop(dep, None)
