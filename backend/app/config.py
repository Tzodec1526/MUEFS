from ipaddress import ip_network
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://muefs:muefs_dev@localhost:5432/muefs"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # S3-compatible document storage (the local stack runs Versity Gateway)
    s3_endpoint_url: str = "http://localhost:7070"
    s3_access_key: str = "muefs_storage"
    s3_secret_key: str = "muefs_storage_secret"
    s3_bucket_name: str = "muefs-documents"

    # Keycloak. Tokens must name KEYCLOAK_URL (the browser-facing address) as issuer.
    keycloak_url: str = "http://localhost:8080"
    # Optional address the API uses to fetch signing keys when KEYCLOAK_URL is not
    # reachable from its network (e.g. http://keycloak:8080 inside Docker Compose).
    keycloak_internal_url: str = ""
    keycloak_realm: str = "muefs"
    keycloak_client_id: str = "muefs-api"

    # App
    # Local tooling sets DEBUG=true. An unset value keeps production startup checks on.
    debug: bool = False
    # Log every SQL statement and its parameters (development diagnostics only).
    database_echo: bool = False
    # Court compliance: NEVER enable in production. Allows X-Demo-User-Id header auth.
    allow_demo_mode: bool = False
    # Required when ALLOW_DEMO_MODE=true and DEBUG=false (hosted demo / staging).
    demo_mode_secret: str = ""
    allowed_origins: str = "http://localhost:3000,http://localhost:5173,http://0.0.0.0:3000"
    # OpenAPI /docs and /redoc (default follows debug; set false in production).
    enable_api_docs: bool | None = None
    # Missing ClamAV and placeholder secrets always refuse to start outside demo/debug;
    # this also raises on the advisory findings (recommended for court deploys).
    security_strict_startup: bool = False
    # Comma-separated proxy addresses or networks (CIDR) whose X-Forwarded-For is
    # trusted, e.g. 10.0.0.0/8 for a platform load balancer.
    trusted_proxy_ips: str = ""

    # Document processing
    max_file_size_mb: int = 100
    local_storage_path: str = "demo_uploads"  # SQLite demos and restored local file collections

    # Upload malware screening (defense in depth on top of the MIME allowlist).
    # The built-in heuristic scan is offline and always-on so the demo needs no extra
    # services; ClamAV is an optional production backend.
    malware_scan_clamav_enabled: bool = False
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_socket: str = ""  # unix socket path; preferred over host/port when set
    # Total deadline for connection, upload and verdict; every failure rejects the upload.
    clamav_timeout_seconds: float = Field(default=30, gt=0, le=300)

    # Reject uploads when libmagic cannot identify type (recommended outside DEBUG).
    strict_mime_detection: bool | None = None

    # JWT: validate `aud` against KEYCLOAK_CLIENT_ID and JWT_AUDIENCES. Keycloak's generic
    # "account" audience is not accepted unless it is listed explicitly.
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
    external_payments_enabled: bool = False

    # Notices are queued only when explicitly enabled. A separate worker sends them.
    email_delivery_enabled: bool = False
    # Explicitly enabled after the court configures and evaluates document delivery.
    service_delivery_enabled: bool = False
    portal_base_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_tls: Literal["starttls", "ssl", "plain"] = "starttls"
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""

    # Hosted public demo (deploy only): per-visitor isolated SQLite sandboxes.
    # When true, each browser session gets its own copy of a seeded template DB;
    # a real court deployment leaves this false and uses one shared database.
    demo_isolated_sessions: bool = False
    demo_max_sessions: int = 100
    demo_session_ttl_minutes: int = 60
    # Uploads each sandbox may keep; its folder is deleted with the sandbox.
    demo_storage_quota_mb: int = Field(default=200, gt=0)
    demo_static_dir: str = "static"  # built frontend the demo server serves

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

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
        return list(dict.fromkeys([*extras, self.keycloak_client_id]))

    @property
    def rate_limit_fail_closed_enabled(self) -> bool:
        if self.rate_limit_fail_closed is not None:
            return self.rate_limit_fail_closed
        return not self.debug

    @field_validator("trusted_proxy_ips")
    @classmethod
    def _check_proxy_networks(cls, value: str) -> str:
        for entry in filter(None, (part.strip() for part in value.split(","))):
            ip_network(entry, strict=False)  # ValueError names the bad entry
        return value

    @field_validator("demo_mode_secret")
    @classmethod
    def _strip_demo_secret(cls, value: str) -> str:
        return value.strip()

    model_config = {"env_file": ".env", "extra": "ignore", "env_ignore_empty": True}


settings = Settings()
