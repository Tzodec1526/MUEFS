"""Fail-fast checks for unsafe production configuration."""

from __future__ import annotations

import logging

from app.config import settings

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
    """Log warnings or raise when production settings are unsafe."""
    issues: list[str] = []

    if settings.allow_demo_mode and not settings.debug and not settings.demo_mode_secret:
        issues.append(
            "ALLOW_DEMO_MODE=true without DEBUG requires DEMO_MODE_SECRET "
            "(prevents unauthenticated header impersonation)"
        )
    if not settings.debug and settings.allow_public_registration:
        issues.append("ALLOW_PUBLIC_REGISTRATION should be false outside DEBUG")
    if not settings.debug and settings.enable_api_docs:
        issues.append("ENABLE_API_DOCS should be false outside DEBUG")
    if settings.malware_scan_clamav_enabled and not settings.malware_scan_fail_closed:
        issues.append(
            "MALWARE_SCAN_FAIL_CLOSED should be true when ClamAV is enabled"
        )

    if not settings.debug:
        for name, value in (
            ("KEYCLOAK_CLIENT_SECRET", settings.keycloak_client_secret),
            ("SECRET_KEY", settings.secret_key),
            ("S3_SECRET_KEY", settings.s3_secret_key),
        ):
            if value in _PLACEHOLDER_SECRETS or len(value) < 16:
                issues.append(f"{name} looks like a placeholder or is too short")

    if issues:
        message = "Security configuration issues:\n- " + "\n- ".join(issues)
        if settings.security_strict_startup:
            raise RuntimeError(message)
        logger.warning(message)
