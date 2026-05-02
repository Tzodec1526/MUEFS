"""Application configuration loaded from environment / .env.

Production safety: when ``debug`` and ``allow_demo_mode`` are both off, several
default values that are safe in dev (e.g. ``secret_key="change-this-…"``) are
hard-failed at startup so they cannot leak into a court-facing deploy.
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings

_INSECURE_SECRET_DEFAULTS = frozenset({
    "change-me-in-production",
    "change-this-to-a-random-secret-in-production",
})


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://muefs:muefs_dev@localhost:5432/muefs"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # S3 / MinIO
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "muefs_minio"
    s3_secret_key: str = "muefs_minio_secret"
    s3_bucket_name: str = "muefs-documents"

    # Keycloak
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "muefs"
    keycloak_client_id: str = "muefs-api"
    keycloak_client_secret: str = "change-me-in-production"

    # App
    secret_key: str = "change-this-to-a-random-secret-in-production"
    debug: bool = True
    # Court compliance: NEVER enable in production. Allows X-Demo-User-Id header auth.
    allow_demo_mode: bool = False
    allowed_origins: str = "http://localhost:3000,http://localhost:5173,http://0.0.0.0:3000"

    # Email
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@michigan-efiling.gov"

    # Document processing
    max_file_size_mb: int = 100

    # Registration: self-serve POST /auth/register (demo only in typical court deploys)
    allow_public_registration: bool = False

    # OIDC: create User on first Bearer login when no keycloak_id match (needs email in token)
    provision_user_on_first_oidc_login: bool = True

    # Rate limiting (set backend=redis in Docker / when Redis is reachable)
    rate_limit_enabled: bool = True
    rate_limit_backend: str = "memory"  # redis | memory
    rate_limit_default_per_minute: int = 120
    rate_limit_search_per_minute: int = 30
    rate_limit_document_per_minute: int = 60
    # Cap memory rate limit dict — bounds RAM under skewed traffic / slow scrapers.
    rate_limit_memory_max_keys: int = 50_000

    # Payments: no PSP integration in this repo — UI/API must reflect simulation
    payments_are_simulated: bool = True

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        """A deploy is treated as production when debug is off AND demo mode is off."""
        return not self.debug and not self.allow_demo_mode

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Settings:
        if not self.is_production:
            return self

        problems: list[str] = []
        if self.secret_key in _INSECURE_SECRET_DEFAULTS:
            problems.append("SECRET_KEY is still set to a default placeholder value.")
        if self.keycloak_client_secret in _INSECURE_SECRET_DEFAULTS:
            problems.append(
                "KEYCLOAK_CLIENT_SECRET is still set to a default placeholder value."
            )
        if self.allow_public_registration:
            problems.append(
                "ALLOW_PUBLIC_REGISTRATION must be false in production "
                "(use IdP / admin invite instead)."
            )
        if any(o.startswith("http://") and "localhost" not in o for o in self.allowed_origins_list):
            problems.append(
                "ALLOWED_ORIGINS contains a non-localhost http:// origin in production; "
                "use https:// origins for the portal."
            )
        if problems:
            raise ValueError(
                "Refusing to start with insecure production configuration:\n  - "
                + "\n  - ".join(problems)
            )
        return self

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
