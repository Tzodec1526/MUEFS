"""Security hardening regression tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import app
from app.security.demo_auth import demo_headers_permitted


@pytest.mark.asyncio
async def test_security_headers_on_health() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert "content-security-policy" in response.headers


def test_api_docs_disabled_outside_debug() -> None:
    settings = Settings(debug=False, enable_api_docs=None)
    assert settings.api_docs_enabled is False


def test_demo_secret_required_outside_debug(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "allow_demo_mode", True)
    monkeypatch.setattr(settings, "demo_mode_secret", "court-demo-secret")

    assert demo_headers_permitted(None) is False
    assert demo_headers_permitted("wrong") is False
    assert demo_headers_permitted("court-demo-secret") is True


def test_strict_mime_defaults_follow_debug() -> None:
    assert Settings(debug=True).strict_mime_detection_enabled is False
    assert Settings(debug=False).strict_mime_detection_enabled is True
