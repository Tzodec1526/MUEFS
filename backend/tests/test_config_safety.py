"""Settings refuses to start with default secrets in production mode."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_rejects_default_secret_key():
    with pytest.raises(ValidationError):
        Settings(
            debug=False,
            allow_demo_mode=False,
            keycloak_client_secret="real-secret-value",
            secret_key="change-this-to-a-random-secret-in-production",
        )


def test_production_rejects_default_keycloak_secret():
    with pytest.raises(ValidationError):
        Settings(
            debug=False,
            allow_demo_mode=False,
            secret_key="real-secret-value",
            keycloak_client_secret="change-me-in-production",
        )


def test_production_rejects_public_registration():
    with pytest.raises(ValidationError):
        Settings(
            debug=False,
            allow_demo_mode=False,
            secret_key="real-secret-value",
            keycloak_client_secret="real-keycloak-value",
            allow_public_registration=True,
        )


def test_production_accepts_secure_config():
    s = Settings(
        debug=False,
        allow_demo_mode=False,
        secret_key="real-secret-value",
        keycloak_client_secret="real-keycloak-value",
        allow_public_registration=False,
        allowed_origins="https://efile.example.gov",
    )
    assert s.is_production is True


def test_demo_mode_allows_default_secrets():
    # Demo deployments often run with placeholder values; the validator must not block them.
    s = Settings(debug=True, allow_demo_mode=True)
    assert s.is_production is False
