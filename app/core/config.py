"""Typed application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    admin_bootstrap_token: str = Field(default="", repr=False)

    mpesa_consumer_key: str = Field(default="", repr=False)
    mpesa_consumer_secret: str = Field(default="", repr=False)
    mpesa_shortcode: str = ""
    mpesa_passkey: str = Field(default="", repr=False)
    mpesa_callback_url: str = ""
    mpesa_environment: Literal["sandbox", "production"] = "sandbox"
    mpesa_transaction_type: Literal["CustomerPayBillOnline", "CustomerBuyGoodsOnline"] = "CustomerPayBillOnline"

    weather_api_key: str = Field(default="", repr=False)
    sms_api_key: str = Field(default="", repr=False)
    sms_api_url: str = ""
    sms_sender_id: str = ""
    sms_username: str = "sandbox"
    sms_environment: Literal["sandbox", "production"] = "sandbox"
    sms_auto_dispatch: bool = False

    disease_model_path: str = ""
    disease_labels_path: str = ""
    disease_image_max_bytes: int = Field(default=8_388_608, ge=1024, le=25_000_000)
    disease_input_size: int = Field(default=224, ge=32, le=1024)

    payment_provider: Literal["mock", "daraja"] = "mock"
    escrow_provider: Literal["mock", "partner"] = "mock"
    sms_provider: Literal["mock", "http", "africas_talking"] = "mock"
    platform_commission_bps: int = Field(default=500, ge=0, le=10000)

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
