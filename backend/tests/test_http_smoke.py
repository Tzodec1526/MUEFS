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


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/v1/filings/1/submit"),
    ("PUT", "/api/v1/admin/users/1"),
    ("PUT", "/api/v1/cases/1/participants/1"),
])
async def test_write_preflight_allows_method_and_idempotency_header(method, path) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            path,
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "content-type,idempotency-key,x-demo-user-id",
            },
        )
    assert response.status_code == 200
    assert method in response.headers["access-control-allow-methods"]
    assert "idempotency-key" in response.headers["access-control-allow-headers"].lower()


@pytest.mark.asyncio
async def test_api_v1_filings_create_requires_auth() -> None:
    """Public docket reads need no account, but creating a filing must fail closed (401).

    Auth is rejected before the DB is touched, so this stays a no-DB smoke test.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/v1/filings", json={})
    assert r.status_code == 401
