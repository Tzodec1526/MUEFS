from ipaddress import ip_network
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://muefs:muefs_dev@localhost:5432/muefs"

    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str = "http://localhost:7070"
    s3_access_key: str = "muefs_storage"
    s3_secret_key: str = "muefs_storage_secret"
    s3_bucket_name: str = "muefs-documents"

    keycloak_url: str = "http://localhost:8080"
    keycloak_internal_url: str = ""
    keycloak_realm: str = "muefs"
    keycloak_client_id: str = "muefs-api"

    debug: bool = False
    database_echo: bool = False
    allow_demo_mode: bool = False
    demo_mode_secret: str = ""
    allowed_origins: str = "http://localhost:3000,http://localhost:5173,http://0.0.0.0:3000"
    enable_api_docs: bool | None = None
    security_strict_startup: bool = False
    trusted_proxy_ips: str = ""

    max_file_size_mb: int = 100
    local_storage_path: str = "demo_uploads"

    malware_scan_clamav_enabled: bool = False
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_socket: str = ""
    clamav_timeout_seconds: float = Field(default=30, gt=0, le=300)

    strict_mime_detection: bool | None = None

    jwt_verify_audience: bool | None = None
    jwt_audiences: str = ""

    allow_public_registration: bool = False

    provision_user_on_first_oidc_login: bool = True

    rate_limit_enabled: bool = True
    rate_limit_backend: str = "memory"
    rate_limit_default_per_minute: int = 120
    rate_limit_search_per_minute: int = 30
    rate_limit_document_per_minute: int = 60
    rate_limit_fail_closed: bool | None = None

    payments_are_simulated: bool = True
    external_payments_enabled: bool = False

    email_delivery_enabled: bool = False
    service_delivery_enabled: bool = False
    portal_base_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_tls: Literal["starttls", "ssl", "plain"] = "starttls"
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""

    demo_isolated_sessions: bool = False
    demo_max_sessions: int = 100
    demo_session_ttl_minutes: int = 60
    demo_storage_quota_mb: int = Field(default=200, gt=0)
    demo_static_dir: str = "static"

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
            ip_network(entry, strict=False)
        return value

    @field_validator("demo_mode_secret")
    @classmethod
    def _strip_demo_secret(cls, value: str) -> str:
        return value.strip()

    model_config = {"env_file": ".env", "extra": "ignore", "env_ignore_empty": True}


settings = Settings()
