"""Typed application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class UnsafePaymentConfigurationError(ValueError):
    """Payment settings are incomplete or unsafe for the selected environment."""


class UnsafeSmsConfigurationError(ValueError):
    """SMS settings are incomplete or unsafe for the selected environment."""


def validate_payment_settings(config) -> None:
    """Fail closed when a provider/environment combination could cause real charges."""
    app_env = str(config.app_env).strip().lower()
    payment_provider = str(config.payment_provider).strip().lower()
    mpesa_environment = str(config.mpesa_environment).strip().lower()
    production = app_env in {"production", "prod"}
    nonproduction = app_env in {"development", "dev", "test", "testing", "local"}

    if mpesa_environment == "production" and not production:
        raise UnsafePaymentConfigurationError(
            "MPESA_ENVIRONMENT=production requires APP_ENV=production."
        )

    if payment_provider == "mock":
        return
    if payment_provider != "daraja":
        raise UnsafePaymentConfigurationError("Unsupported payment provider configuration.")
    if not (production or nonproduction):
        raise UnsafePaymentConfigurationError(
            "Daraja payments require APP_ENV=development, test, or production."
        )
    if production and mpesa_environment != "production":
        raise UnsafePaymentConfigurationError(
            "Production Daraja requires MPESA_ENVIRONMENT=production."
        )
    if nonproduction and mpesa_environment != "sandbox":
        raise UnsafePaymentConfigurationError(
            "Non-production Daraja requires MPESA_ENVIRONMENT=sandbox."
        )

    if mpesa_environment == "sandbox":
        credentials = (
            config.mpesa_sandbox_consumer_key,
            config.mpesa_sandbox_consumer_secret,
            config.mpesa_sandbox_shortcode,
            config.mpesa_sandbox_passkey,
            config.mpesa_sandbox_callback_url,
        )
    else:
        # The legacy MPESA_* names remain production-only for existing Render
        # deployments. Sandbox credentials are never sourced from these fields.
        credentials = (
            config.mpesa_production_consumer_key or config.mpesa_consumer_key,
            config.mpesa_production_consumer_secret or config.mpesa_consumer_secret,
            config.mpesa_production_shortcode or config.mpesa_shortcode,
            config.mpesa_production_passkey or config.mpesa_passkey,
            config.mpesa_production_callback_url or config.mpesa_callback_url,
        )
    if not all(str(value).strip() for value in credentials):
        raise UnsafePaymentConfigurationError(
            f"Daraja {mpesa_environment} credentials and callback URL must all be configured."
        )
    if mpesa_environment == "production" and not credentials[-1].strip().startswith("https://"):
        raise UnsafePaymentConfigurationError("Production Daraja callback URL must use HTTPS.")


def validate_sms_settings(config) -> None:
    environment = str(config.sms_environment).strip().lower()
    app_environment = str(config.app_env).strip().lower()
    provider = str(config.sms_provider).strip().lower()
    if environment == "production" and app_environment not in {"production", "prod"}:
        raise UnsafeSmsConfigurationError("SMS_ENVIRONMENT=production requires APP_ENV=production.")
    if provider == "mock":
        return
    if provider not in {"http", "africas_talking"}:
        raise UnsafeSmsConfigurationError("Unsupported SMS provider configuration.")
    if app_environment not in {"development", "dev", "test", "testing", "local", "production", "prod"}:
        raise UnsafeSmsConfigurationError("SMS provider requires APP_ENV=development, test, or production.")
    if environment == "sandbox" and app_environment in {"production", "prod"}:
        raise UnsafeSmsConfigurationError("Production APP_ENV cannot use the SMS sandbox.")
    if environment == "sandbox":
        api_key = config.sms_sandbox_api_key
        username = config.sms_sandbox_username
        endpoint = config.sms_sandbox_api_url
    else:
        api_key = config.sms_production_api_key or config.sms_api_key
        username = config.sms_production_username or config.sms_username
        endpoint = config.sms_production_api_url or config.sms_api_url
    if provider == "africas_talking" and (not api_key.strip() or not username.strip()):
        raise UnsafeSmsConfigurationError(f"Africa's Talking {environment} credentials are not configured.")
    if provider == "http" and (not api_key.strip() or not endpoint.strip().startswith("https://")):
        raise UnsafeSmsConfigurationError("HTTP SMS requires an API key and HTTPS endpoint for the selected environment.")


class Settings(BaseSettings):
    app_name: str = "Smart Agriculture Advisory and Market Linkage API"
    app_env: str = "development"
    debug: bool = True
    # Comma-separated browser origins; empty means no cross-origin browser access.
    cors_allowed_origins: str = ""

    mongodb_uri: str = "mongodb://localhost:27017"
    database_name: str = "smart_agriculture"
    # Atlas SRV discovery plus TLS and replica-set selection can exceed 2.5 s
    # on a cold client or slower network. Fail readiness only after a realistic
    # selection window while keeping the limit configurable per deployment.
    mongodb_server_selection_timeout_ms: int = Field(default=15000, ge=1000, le=60000)

    jwt_secret_key: str = Field(default="", repr=False)
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    admin_bootstrap_token: str = Field(default="", repr=False)

    mpesa_consumer_key: str = Field(default="", repr=False)
    mpesa_consumer_secret: str = Field(default="", repr=False)
    mpesa_shortcode: str = ""
    mpesa_passkey: str = Field(default="", repr=False)
    mpesa_callback_url: str = ""
    mpesa_sandbox_consumer_key: str = Field(default="", repr=False)
    mpesa_sandbox_consumer_secret: str = Field(default="", repr=False)
    mpesa_sandbox_shortcode: str = ""
    mpesa_sandbox_passkey: str = Field(default="", repr=False)
    mpesa_sandbox_callback_url: str = ""
    mpesa_production_consumer_key: str = Field(default="", repr=False)
    mpesa_production_consumer_secret: str = Field(default="", repr=False)
    mpesa_production_shortcode: str = ""
    mpesa_production_passkey: str = Field(default="", repr=False)
    mpesa_production_callback_url: str = ""
    mpesa_environment: Literal["sandbox", "production"] = "sandbox"
    mpesa_transaction_type: Literal["CustomerPayBillOnline", "CustomerBuyGoodsOnline"] = "CustomerPayBillOnline"

    weather_api_key: str = Field(default="", repr=False)
    weather_cache_ttl_seconds: int = Field(default=300, ge=0, le=3600)
    sms_api_key: str = Field(default="", repr=False)
    sms_api_url: str = ""
    sms_sender_id: str = ""
    sms_username: str = "sandbox"
    sms_sandbox_api_key: str = Field(default="", repr=False)
    sms_sandbox_api_url: str = ""
    sms_sandbox_username: str = "sandbox"
    sms_production_api_key: str = Field(default="", repr=False)
    sms_production_api_url: str = ""
    sms_production_username: str = ""
    sms_production_sender_id: str = ""
    sms_environment: Literal["sandbox", "production"] = "sandbox"
    sms_auto_dispatch: bool = False
    sms_webhook_secret: str = Field(default="", repr=False)
    sms_inbound_hourly_limit: int = Field(default=8, ge=1, le=100)

    disease_model_path: str = ""
    disease_labels_path: str = ""
    disease_image_max_bytes: int = Field(default=8_388_608, ge=1024, le=25_000_000)
    disease_input_size: int = Field(default=224, ge=32, le=1024)
    disease_confidence_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    product_image_max_bytes: int = Field(default=5_242_880, ge=1024, le=15_000_000)

    payment_provider: Literal["mock", "daraja"] = "mock"
    escrow_provider: Literal["mock", "partner"] = "mock"
    sms_provider: Literal["mock", "http", "africas_talking"] = "mock"
    platform_commission_bps: int = Field(default=500, ge=0, le=10000)

    @model_validator(mode="after")
    def payment_environment_is_safe(self):
        validate_payment_settings(self)
        validate_sms_settings(self)
        return self

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        hide_input_in_errors=True,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
