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


@pytest.mark.parametrize(
    "provider, origin",
    [
        ("https://identity.example.gov/auth/", "https://identity.example.gov:443"),
        ("http://127.0.0.1:54254", "http://127.0.0.1:54254"),
    ],
)
async def test_browser_policy_allows_configured_identity_exchange_only(
    monkeypatch, provider, origin
):
    from fastapi import FastAPI

    from app.config import settings
    from app.middleware.security_headers import SecurityHeadersMiddleware

    monkeypatch.setattr(settings, "keycloak_url", provider)
    application = FastAPI()
    application.add_middleware(SecurityHeadersMiddleware)
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        callback = await client.get("/auth/callback")
        api = await client.get("/api/v1/auth/me")
    directives = callback.headers["content-security-policy"].split("; ")
    assert f"connect-src 'self' {origin}" in directives
    assert "script-src 'self'" in directives
    assert "style-src 'self' 'unsafe-inline'" in directives
    assert "font-src 'self'" in directives
    assert "fonts.g" not in callback.headers["content-security-policy"]
    assert (
        api.headers["content-security-policy"]
        == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )


def test_api_docs_disabled_outside_debug() -> None:
    settings = Settings(debug=False, enable_api_docs=None)
    assert settings.api_docs_enabled is False


def test_demo_secret_required_outside_debug(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "allow_demo_mode", True)
    monkeypatch.setattr(settings, "demo_isolated_sessions", False)
    monkeypatch.setattr(settings, "demo_mode_secret", "court-demo-secret")

    assert demo_headers_permitted(None) is False
    assert demo_headers_permitted("wrong") is False
    assert demo_headers_permitted("court-demo-secret") is True


def test_demo_headers_allowed_without_secret_when_isolated(monkeypatch) -> None:
    """Hosted public demo must work when Render leaves DEMO_MODE_SECRET unset."""
    from app.config import settings

    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "allow_demo_mode", True)
    monkeypatch.setattr(settings, "demo_mode_secret", "")
    monkeypatch.setattr(settings, "demo_isolated_sessions", True)
    assert demo_headers_permitted(None) is True
    assert demo_headers_permitted("") is True

    monkeypatch.setattr(settings, "demo_isolated_sessions", False)
    assert demo_headers_permitted(None) is False


def test_strict_mime_defaults_follow_debug() -> None:
    assert Settings(debug=True).strict_mime_detection_enabled is False
    assert Settings(debug=False).strict_mime_detection_enabled is True
