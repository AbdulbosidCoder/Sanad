"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # The repository-root .env is read too, so `cd backend && uvicorn ...` (or `python -m
    # app.seed`) uses the same DATABASE_URL as the rest of the project. Real environment
    # variables always win over both files.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_env: Literal["dev", "test", "staging", "prod"] = "dev"
    app_name: str = "Sanad API"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://sanad:sanad@localhost:5432/sanad"
    redis_url: str = "redis://localhost:6379/0"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Payments: the fake provider must never be enabled in production.
    fake_payments_enabled: bool = True
    # HMAC key the fake provider signs its webhooks with (dev/test only).
    fake_payments_webhook_secret: str = "dev-fake-webhook-secret"  # noqa: S105
    # How long stock stays held for an unpaid order.
    reservation_ttl_minutes: int = 30

    # --- Translations (i18n module) ---
    # "none": product texts wait untranslated (buyers see the original);
    # "claude": machine translation through the Claude API (needs ANTHROPIC_API_KEY).
    # Outgoing e-mail: console = written to the log (dev); smtp = a real mail server.
    email_backend: Literal["console", "smtp"] = "console"
    email_from: str = "Sanad <no-reply@sanad.local>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    public_web_url: str = "http://localhost:3000"

    translator: Literal["none", "claude"] = "none"
    anthropic_api_key: str = ""
    translation_model: str = "claude-haiku-5-5"

    # --- Auth (ADR 0005) ---
    # Ed25519 private key seed, base64url, 32 bytes. Generate one with:
    #   python -c "import secrets,base64;print(base64.urlsafe_b64encode(
    #       secrets.token_bytes(32)).decode())"
    # Empty in dev/test -> a throwaway key per process (access tokens die on restart).
    jwt_signing_key: str = ""
    jwt_key_id: str = "k1"
    jwt_issuer: str = "sanad"
    access_token_ttl_seconds: int = 15 * 60
    session_ttl_days: int = 30
    # Browsers accept Secure cookies on http://localhost, so this stays on in dev too.
    auth_cookie_secure: bool = True
    login_max_failures: int = 5
    login_lock_minutes: int = 15

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @model_validator(mode="after")
    def _prod_requires_secrets(self) -> "Settings":
        if self.app_env in ("staging", "prod") and not self.jwt_signing_key:
            raise ValueError("JWT_SIGNING_KEY must be set outside dev/test")
        if self.app_env == "prod" and self.fake_payments_enabled:
            raise ValueError("FAKE_PAYMENTS_ENABLED must be false in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
