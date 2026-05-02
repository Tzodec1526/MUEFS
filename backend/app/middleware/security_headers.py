"""Apply baseline security headers to every response.

Headers chosen for a court-records API:
- X-Content-Type-Options: prevents MIME sniffing on document downloads
- X-Frame-Options: defends against UI redress / clickjacking on the portal
- Referrer-Policy: avoids leaking case URLs in cross-origin Referer headers
- Permissions-Policy: zero out browser features the portal does not use
- Strict-Transport-Security: HTTPS pinning; only emitted in production (debug=false)

CSP is intentionally NOT set here because the React frontend is served by a separate
origin (nginx) where the CSP belongs. Keeping it out of the API response avoids
contradicting the frontend's policy.
"""

from __future__ import annotations

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault(
            "Permissions-Policy",
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()",
        )
        if not settings.debug:
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
