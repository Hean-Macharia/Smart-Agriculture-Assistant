"""SMS provider adapter. HTTP success means accepted, never handset-delivered."""

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse
import httpx

from app.core.config import settings


class SmsProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class SmsResult:
    simulated: bool
    provider_reference: str | None


class SmsProvider(Protocol):
    name: str

    def send_sms(self, *, to: str, message: str, idempotency_key: str) -> SmsResult: ...


class MockSmsProvider:
    name = "mock"

    def send_sms(self, *, to: str, message: str, idempotency_key: str) -> SmsResult:
        del to, message
        return SmsResult(True, f"MOCK-SMS-{idempotency_key[:24]}")


class HttpSmsProvider:
    """Generic JSON/Bearer adapter; map this request to the selected SMS gateway contract."""

    name = "http"

    def send_sms(self, *, to: str, message: str, idempotency_key: str) -> SmsResult:
        endpoint = settings.sms_api_url.strip()
        api_key = settings.sms_api_key.strip()
        if not endpoint or not api_key:
            raise SmsProviderError("SMS HTTP adapter is not configured")
        if urlparse(endpoint).scheme != "https" or not urlparse(endpoint).hostname:
            raise SmsProviderError("SMS API URL must use HTTPS")
        headers = {"Authorization": f"Bearer {api_key}", "Idempotency-Key": idempotency_key}
        payload = {"to": to, "message": message, "sender_id": settings.sms_sender_id or None}
        try:
            response = httpx.post(endpoint, headers=headers, json=payload, timeout=httpx.Timeout(10.0, connect=4.0))
            response.raise_for_status()
            try:
                result = response.json()
            except ValueError:
                result = {}
            reference = result.get("message_id") or result.get("id") if isinstance(result, dict) else None
            return SmsResult(False, str(reference)[:160] if reference else None)
        except httpx.HTTPError as exc:
            # Do not log request URLs, headers, recipient numbers, body, or provider error text.
            raise SmsProviderError("SMS provider request failed") from exc


class AfricasTalkingSmsProvider:
    """Africa's Talking SMS v1 adapter; sandbox sends to its simulator, not a handset."""

    def __init__(self):
        self.environment = settings.sms_environment
        self.username = settings.sms_username.strip()
        self.api_key = settings.sms_api_key.strip()
        self.endpoint = (
            "https://api.sandbox.africastalking.com/version1/messaging"
            if self.environment == "sandbox"
            else "https://api.africastalking.com/version1/messaging"
        )

    @property
    def name(self) -> str:
        return f"africas_talking_{self.environment}"

    def send_sms(self, *, to: str, message: str, idempotency_key: str) -> SmsResult:
        del idempotency_key  # Internal notification idempotency prevents repeat provider calls.
        if not self.api_key or not self.username:
            raise SmsProviderError("Africa's Talking credentials are not configured")
        if self.environment == "production" and self.username.lower() == "sandbox":
            raise SmsProviderError("Production SMS requires the production app username")
        headers = {"apiKey": self.api_key, "Accept": "application/json"}
        form = {"username": self.username, "to": to, "message": message}
        if settings.sms_sender_id.strip():
            form["from"] = settings.sms_sender_id.strip()
        try:
            response = httpx.post(
                self.endpoint,
                headers=headers,
                data=form,
                timeout=httpx.Timeout(10.0, connect=4.0),
            )
            response.raise_for_status()
            data = response.json()
            recipients = data.get("SMSMessageData", {}).get("Recipients", []) if isinstance(data, dict) else []
            if not recipients:
                raise SmsProviderError("Africa's Talking returned no recipient result")
            recipient = recipients[0]
            try:
                result_code = int(recipient.get("statusCode", -1))
            except (TypeError, ValueError):
                result_code = -1
            if result_code not in {100, 101, 102}:
                raise SmsProviderError("Africa's Talking did not accept the SMS")
            reference = recipient.get("messageId")
            return SmsResult(self.environment == "sandbox", str(reference)[:160] if reference else None)
        except SmsProviderError:
            raise
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            # Never log the request body, phone, API key, or gateway response text.
            raise SmsProviderError("Africa's Talking SMS request failed") from exc


def get_sms_provider() -> SmsProvider:
    if settings.sms_provider == "http":
        return HttpSmsProvider()
    if settings.sms_provider == "africas_talking":
        return AfricasTalkingSmsProvider()
    return MockSmsProvider()
