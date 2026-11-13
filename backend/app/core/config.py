"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "staging", "prod"] = "dev"
    app_name: str = "Sanad API"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://sanad:sanad@localhost:5432/sanad"
    redis_url: str = "redis://localhost:6379/0"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Payments: the fake provider must never be enabled in production.
    fake_payments_enabled: bool = True

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
