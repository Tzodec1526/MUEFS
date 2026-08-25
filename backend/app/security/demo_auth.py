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
    if not settings.demo_mode_secret:
        return False
    return secrets.compare_digest(provided_secret or "", settings.demo_mode_secret)
