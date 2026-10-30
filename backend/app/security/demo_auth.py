from __future__ import annotations

import secrets

from app.config import settings


def demo_headers_permitted(provided_secret: str | None) -> bool:
    if not settings.allow_demo_mode:
        return False
    if settings.debug:
        return True
    expected = settings.demo_mode_secret
    if not expected:
        return bool(settings.demo_isolated_sessions)
    return secrets.compare_digest(provided_secret or "", expected)
