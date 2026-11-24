import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings, validate_payment_settings
from app.services.payment_providers import (
    DarajaPaymentProvider,
    MockPaymentProvider,
    PaymentProviderError,
    get_payment_provider,
)


SANDBOX = {
    "mpesa_sandbox_consumer_key": "sandbox-key",
    "mpesa_sandbox_consumer_secret": "sandbox-secret",
    "mpesa_sandbox_shortcode": "123456",
    "mpesa_sandbox_passkey": "sandbox-passkey",
    "mpesa_sandbox_callback_url": "https://sandbox.example.test/payments/callback/daraja",
}
PRODUCTION = {
    "mpesa_production_consumer_key": "production-key",
    "mpesa_production_consumer_secret": "production-secret",
    "mpesa_production_shortcode": "654321",
    "mpesa_production_passkey": "production-passkey",
    "mpesa_production_callback_url": "https://production.example.test/payments/callback/daraja",
}


def build_settings(**overrides):
    values = {
        "app_env": "development",
        "payment_provider": "daraja",
        "mpesa_environment": "sandbox",
        **SANDBOX,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def test_development_production_daraja_is_rejected_even_with_production_credentials():
    credential_marker = "must-not-appear-in-errors"
    with pytest.raises(ValidationError, match="requires APP_ENV=production") as error:
        build_settings(mpesa_environment="production", **{**PRODUCTION, "mpesa_production_consumer_secret": credential_marker})
    assert credential_marker not in str(error.value)


def test_development_sandbox_daraja_configuration_is_valid():
    configured = build_settings()
    validate_payment_settings(configured)
    # Ensure the sandbox adapter has a distinct credential source.
    assert configured.mpesa_sandbox_consumer_key == "sandbox-key"
    assert configured.mpesa_production_consumer_key == ""


def test_production_sandbox_daraja_configuration_is_rejected():
    with pytest.raises(ValidationError, match="requires MPESA_ENVIRONMENT=production"):
        build_settings(app_env="production", **PRODUCTION)


def test_correct_production_daraja_configuration_is_valid():
    configured = build_settings(app_env="production", mpesa_environment="production", **PRODUCTION)
    validate_payment_settings(configured)


def test_daraja_missing_credentials_fails_closed():
    with pytest.raises(ValidationError, match="credentials and callback URL"):
        build_settings(mpesa_sandbox_passkey="", mpesa_sandbox_callback_url="")


@pytest.mark.parametrize(
    "values",
    [
        {"app_env": "staging", "payment_provider": "daraja", "mpesa_environment": "sandbox", **SANDBOX},
        {"app_env": "development", "payment_provider": "daraja", "mpesa_environment": "production", **PRODUCTION},
    ],
)
def test_invalid_environment_combinations_fail(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_mock_selection_does_not_read_production_credentials(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "payment_provider", "mock")
    monkeypatch.setattr(settings, "mpesa_environment", "sandbox")
    monkeypatch.setattr(settings, "mpesa_sandbox_consumer_key", "")
    monkeypatch.setattr(settings, "mpesa_consumer_key", "production-only-key")
    assert isinstance(get_payment_provider(), MockPaymentProvider)


def test_provider_selection_validates_before_returning_daraja(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "payment_provider", "daraja")
    monkeypatch.setattr(settings, "mpesa_environment", "sandbox")
    for field, value in SANDBOX.items():
        monkeypatch.setattr(settings, field, value)
    provider = get_payment_provider()
    assert isinstance(provider, DarajaPaymentProvider)
    assert provider.base_url == "https://sandbox.safaricom.co.ke"
    assert provider._credentials() == tuple(SANDBOX[key] for key in (
        "mpesa_sandbox_consumer_key", "mpesa_sandbox_consumer_secret", "mpesa_sandbox_shortcode",
        "mpesa_sandbox_passkey", "mpesa_sandbox_callback_url",
    ))


def test_sandbox_never_falls_back_to_legacy_production_credentials(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "payment_provider", "daraja")
    monkeypatch.setattr(settings, "mpesa_environment", "sandbox")
    for field in SANDBOX:
        monkeypatch.setattr(settings, field, "")
    for field, value in {
        "mpesa_consumer_key": "prod-key", "mpesa_consumer_secret": "prod-secret",
        "mpesa_shortcode": "123", "mpesa_passkey": "prod-pass", "mpesa_callback_url": "https://prod.test/callback",
    }.items():
        monkeypatch.setattr(settings, field, value)
    with pytest.raises(PaymentProviderError):
        get_payment_provider()

