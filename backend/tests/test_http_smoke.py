"""Smoke tests: FastAPI app mounts and public endpoints respond (no DB required)."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy", "service": "muefs-api"}


@pytest.mark.asyncio
async def test_openapi_docs_available() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/docs")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_api_v1_cases_search_requires_auth() -> None:
    """Demo uses X-Demo-User-Id only when ALLOW_DEMO_MODE; default in tests is unauthenticated."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/cases/search")
    assert r.status_code == 401
