from pydantic import field_validator
from pydantic_settings import BaseSettings


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
    # Required when ALLOW_DEMO_MODE=true and DEBUG=false (hosted demo / staging).
    demo_mode_secret: str = ""
    allowed_origins: str = "http://localhost:3000,http://localhost:5173,http://0.0.0.0:3000"
    # OpenAPI /docs and /redoc (default follows debug; set false in production).
    enable_api_docs: bool | None = None
    # Raise on unsafe production config at startup (recommended for court deploys).
    security_strict_startup: bool = False
    # Comma-separated trusted proxy IPs for X-Forwarded-For (Render, nginx, etc.).
    trusted_proxy_ips: str = ""

    # Email
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@michigan-efiling.gov"

    # Document processing
    max_file_size_mb: int = 100

    # Upload malware screening (defense in depth on top of the MIME allowlist).
    # The built-in heuristic scan is offline and always-on so the demo needs no extra
    # services; ClamAV is an optional production backend.
    malware_scan_enabled: bool = True
    malware_scan_clamav_enabled: bool = False
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_socket: str = ""  # unix socket path; preferred over host/port when set
    # When ClamAV is enabled but unreachable: True rejects the upload, False falls back
    # to the built-in scan only.
    malware_scan_fail_closed: bool = False

    # Reject uploads when libmagic cannot identify type (recommended outside DEBUG).
    strict_mime_detection: bool | None = None

    # JWT: validate `aud` claim against Keycloak client id(s).
    jwt_verify_audience: bool | None = None
    # Optional extra audiences (comma-separated), e.g. muefs-frontend,muefs-api
    jwt_audiences: str = ""

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
    # When Redis rate limiting is enabled, reject requests if Redis is unreachable.
    rate_limit_fail_closed: bool | None = None

    # Payments: no PSP integration in this repo — UI/API must reflect simulation
    payments_are_simulated: bool = True

    # Hosted public demo (deploy only): per-visitor isolated SQLite sandboxes.
    # When true, each browser session gets its own copy of a seeded template DB;
    # a real court deployment leaves this false and uses one shared database.
    demo_isolated_sessions: bool = False
    demo_max_sessions: int = 100
    demo_session_ttl_minutes: int = 60
    demo_static_dir: str = "static"  # built frontend the demo server serves

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def trusted_proxy_ips_list(self) -> list[str]:
        return [ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()]

    @property
    def api_docs_enabled(self) -> bool:
        if self.enable_api_docs is not None:
            return self.enable_api_docs
        return self.debug

    @property
    def strict_mime_detection_enabled(self) -> bool:
        if self.strict_mime_detection is not None:
            return self.strict_mime_detection
        return not self.debug

    @property
    def jwt_audience_verify_enabled(self) -> bool:
        if self.jwt_verify_audience is not None:
            return self.jwt_verify_audience
        return not self.debug

    @property
    def jwt_audiences_list(self) -> list[str]:
        extras = [a.strip() for a in self.jwt_audiences.split(",") if a.strip()]
        base = [self.keycloak_client_id, "account"]
        return list(dict.fromkeys([*extras, *base]))

    @property
    def rate_limit_fail_closed_enabled(self) -> bool:
        if self.rate_limit_fail_closed is not None:
            return self.rate_limit_fail_closed
        return not self.debug

    @field_validator("demo_mode_secret")
    @classmethod
    def _strip_demo_secret(cls, value: str) -> str:
        return value.strip()

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
