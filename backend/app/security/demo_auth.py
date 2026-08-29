"""Demo-mode header authentication guards."""

from __future__ import annotations

import secrets

from app.config import settings


def demo_headers_permitted(provided_secret: str | None) -> bool:
    """Whether X-Demo-User-Id may be honored for this request."""
    if not settings.allow_demo_mode:
        return False
    if settings.debug:
        return True
    expected = settings.demo_mode_secret
    if not expected:
        # Public hosted demo (isolated sandboxes) must keep working even when
        # DEMO_MODE_SECRET was never set in the host env (empty config.js).
        # Never enable ALLOW_DEMO_MODE without isolation on a real court deploy.
        return bool(settings.demo_isolated_sessions)
    return secrets.compare_digest(provided_secret or "", expected)
