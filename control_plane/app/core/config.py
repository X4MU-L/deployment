from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration — loaded from env vars with CP_ prefix."""

    DATABASE_URL: str = "sqlite+aiosqlite:///./control_plane.db"
    REDIS_URL: str | None = None
    internal_service_token: str = "dev-internal-service-token"
    apps_base_domain: str = "apps.example.com"
    route_cache_ttl_seconds: int = 30
    background_builder_provider: str = "fake-builder"
    celery_broker_url: str = "sqla+sqlite:///./celery-broker.sqlite"
    celery_result_backend: str = "db+sqlite:///./celery-results.sqlite"
    celery_task_always_eager: bool = False
    celery_task_eager_propagates: bool = True
    celery_builder_queue_name: str = "fake-builder"
    celery_builder_service_name: str = "fake-builder"
    celery_builder_artifact_bucket: str = "fake-static-artifacts"
    celery_builder_base_url: str = "http://localhost:8000"
    artifact_store_provider: str = "local"
    artifact_store_root: str = "./.artifacts"
    r2_endpoint_url: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_session_token: str | None = None
    r2_region_name: str = "auto"
    cloudflare_api_base_url: str = "https://api.cloudflare.com/client/v4"
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_queue_name: str = "build-requested"
    cloudflare_queue_id: str = ""
    cloudflare_pull_batch_size: int = 5
    cloudflare_pull_visibility_timeout_ms: int = 30000
    cloudflare_pull_poll_interval_seconds: int = 5
    cloudflare_artifact_bucket: str = "static-artifacts"

    log_level: str = "INFO"
    logger_name: str = "CONTROL_PLANE"
    # JWT
    jwt_secret: str = "change-me-in-production-use-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    jwt_private_key_path: str = ""
    jwt_public_key_path: str = ""
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    session_token_expire_seconds: int = 3600

    # UI / OAuth
    public_base_url: str = "http://localhost:8000"
    client_base_url: str = "http://localhost:3000"
    github_client_id: str = ""
    github_client_secret: str = ""
    github_webhook_secret: str = "change-me-in-production-use-a-long-random-secret"
    github_app_id: str = ""
    github_app_private_key_path: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    facebook_client_id: str = ""
    facebook_client_secret: str = ""

    model_config = {"env_prefix": "CP_", "env_file": ".env", "extra": "ignore"}


settings = Settings()


def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return settings
