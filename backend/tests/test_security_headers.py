"""Security headers + request id are applied to every response."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_security_headers_present_on_health() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
    assert "Permissions-Policy" in r.headers


@pytest.mark.asyncio
async def test_request_id_minted_when_missing() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    rid = r.headers.get("X-Request-ID")
    assert rid is not None
    assert len(rid) >= 16


@pytest.mark.asyncio
async def test_request_id_echoes_safe_client_value() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health", headers={"X-Request-ID": "abc-123_def"})
    assert r.headers.get("X-Request-ID") == "abc-123_def"


@pytest.mark.asyncio
async def test_request_id_replaces_unsafe_client_value() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health", headers={"X-Request-ID": "bad value with spaces"})
    rid = r.headers.get("X-Request-ID")
    assert rid is not None
    assert rid != "bad value with spaces"
