from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration — loaded from env vars with CP_ prefix."""

    DATABASE_URL: str = "sqlite+aiosqlite:///./control_plane.db"
    REDIS_URL: str | None = None
    internal_service_token: str = "dev-internal-service-token"
    apps_base_domain: str = "apps.example.com"
    route_cache_ttl_seconds: int = 30
    celery_broker_url: str = "sqla+sqlite:///./celery-broker.sqlite"
    celery_result_backend: str = "db+sqlite:///./celery-results.sqlite"
    celery_task_always_eager: bool = False
    celery_task_eager_propagates: bool = True
    fake_builder_queue_name: str = "fake-builder"
    fake_builder_service_name: str = "fake-builder"
    fake_builder_artifact_bucket: str = "fake-static-artifacts"
    fake_builder_base_url: str = "http://localhost:8000"

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
