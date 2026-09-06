"""OWASP-aligned HTTP security headers for API and SPA responses."""

from __future__ import annotations

from fastapi import Request, Response
from pydantic import HttpUrl
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.config import settings

_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        identity = HttpUrl(settings.keycloak_url)
        # PKCE exchanges the authorization code from the browser. Permit the configured
        # provider origin without opening script loading or unrelated connections.
        self.spa_csp = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            f"connect-src 'self' {identity.scheme}://{identity.host}:{identity.port}; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        response.headers["Content-Security-Policy"] = (
            _API_CSP if request.url.path.startswith("/api/") else self.spa_csp
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "private, no-store"
        if not request.url.path.startswith("/api/"):
            response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
        return response
