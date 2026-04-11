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

    # Payments: no PSP integration in this repo — UI/API must reflect simulation
    payments_are_simulated: bool = True

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
