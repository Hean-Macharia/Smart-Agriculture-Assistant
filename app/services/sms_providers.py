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


def get_sms_provider() -> SmsProvider:
    return HttpSmsProvider() if settings.sms_provider == "http" else MockSmsProvider()
