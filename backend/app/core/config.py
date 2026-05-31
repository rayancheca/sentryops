"""Application settings. Secrets come from the environment only, never source."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated configuration loaded from environment / .env.

    Every secret (``secret_key``, ``anthropic_api_key``) is read from the
    environment. Nothing here is logged; see ``app.core.logging``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Runtime
    environment: str = "development"
    log_level: str = "INFO"

    # Security / auth
    secret_key: str = "dev-only-insecure-secret-change-me-in-production-32b+"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    rate_limit_auth: str = "10/minute"
    rate_limit_scan: str = "6/minute"

    # Infrastructure
    database_url: str = "postgresql+psycopg://sentryops:sentryops@localhost:5432/sentryops"
    redis_url: str = "redis://localhost:6379/0"

    # CORS — comma-separated origins; exposed as a list via ``cors_origin_list``.
    cors_origins: str = "http://localhost:3000"

    # Observability worker
    healthcheck_interval_seconds: int = 30
    incident_open_threshold: int = 3
    incident_close_threshold: int = 2

    # AI incident triage (Pillar 4) — off by default, degrades gracefully.
    ai_triage_enabled: bool = False
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    ai_max_output_tokens: int = 1500
    ai_daily_token_budget: int = 200_000
    ai_prompt_version: str = "v1"

    # Bootstrap accounts (used by the seed script / first run)
    first_admin_email: str = "admin@sentryops.local"
    first_admin_password: str = "admin12345"
    first_viewer_email: str = "viewer@sentryops.local"
    first_viewer_password: str = "viewer12345"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def ai_active(self) -> bool:
        """AI triage is live only when explicitly enabled AND a key is present."""
        return self.ai_triage_enabled and bool(self.anthropic_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton (cached)."""
    return Settings()
