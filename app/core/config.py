"""Typed application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Smart Agriculture Advisory and Market Linkage API"
    app_env: str = "development"
    debug: bool = True

    mongodb_uri: str = "mongodb://localhost:27017"
    database_name: str = "smart_agriculture"
    mongodb_server_selection_timeout_ms: int = 2500

    jwt_secret_key: str = Field(default="", repr=False)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    mpesa_consumer_key: str = Field(default="", repr=False)
    mpesa_consumer_secret: str = Field(default="", repr=False)
    mpesa_shortcode: str = ""
    mpesa_passkey: str = Field(default="", repr=False)
    mpesa_callback_url: str = ""
    mpesa_environment: str = "sandbox"

    weather_api_key: str = Field(default="", repr=False)
    sms_api_key: str = Field(default="", repr=False)

    payment_provider: str = "mock"
    escrow_provider: str = "mock"

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
