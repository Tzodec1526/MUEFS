"""Fail-fast checks for unsafe production configuration."""

from __future__ import annotations

import logging

from app.config import settings
from app.services.email_delivery_service import validate_email_config

logger = logging.getLogger(__name__)

_PLACEHOLDER_SECRETS = frozenset(
    {
        "change-me-in-production",
        "change-this-to-a-random-secret-in-production",
        "muefs_dev",
        "muefs_minio_secret",
        "admin",
    }
)


def validate_security_config() -> None:
    """Raise on unsafe production settings; warn for the rest unless strict startup is on."""
    issues: list[str] = []
    fatal: list[str] = []
    validate_email_config()

    if settings.allow_demo_mode and not settings.debug and not settings.demo_mode_secret:
        issues.append(
            "ALLOW_DEMO_MODE=true without DEBUG requires DEMO_MODE_SECRET "
            "(prevents unauthenticated header impersonation)"
        )
    if not settings.debug and settings.allow_public_registration:
        issues.append("ALLOW_PUBLIC_REGISTRATION should be false outside DEBUG")
    if not settings.debug and settings.enable_api_docs:
        issues.append("ENABLE_API_DOCS should be false outside DEBUG")
    # The hosted demo runs DEBUG=false with ALLOW_DEMO_MODE=true on SQLite and local
    # storage; only a court deployment (neither flag) must refuse to start.
    production = not settings.debug and not settings.allow_demo_mode
    if production and not settings.malware_scan_clamav_enabled:
        fatal.append("MALWARE_SCAN_CLAMAV_ENABLED must be true outside demo/debug mode")

    if not settings.debug:
        for name, value in (
            ("KEYCLOAK_CLIENT_SECRET", settings.keycloak_client_secret),
            ("SECRET_KEY", settings.secret_key),
            ("S3_SECRET_KEY", settings.s3_secret_key),
        ):
            if value in _PLACEHOLDER_SECRETS or len(value) < 16:
                (fatal if production else issues).append(
                    f"{name} looks like a placeholder or is too short"
                )

    if issues or fatal:
        message = "Security configuration issues:\n- " + "\n- ".join(fatal + issues)
        if fatal or settings.security_strict_startup:
            raise RuntimeError(message)
        logger.warning(message)
