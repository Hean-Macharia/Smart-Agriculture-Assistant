"""Payment provider adapters. The mock never represents a real M-PESA transaction."""

import base64
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Protocol

import httpx

from app.core.config import settings


class PaymentProviderError(RuntimeError):
    """A configured provider could not accept or verify a request."""


@dataclass(frozen=True)
class InitiationResult:
    merchant_request_id: str
    checkout_request_id: str
    response_description: str


class PaymentProvider(Protocol):
    name: str

    def initiate_stk_push(self, *, amount_kes: int, phone_number: str, account_reference: str, description: str) -> InitiationResult: ...

    def query_stk_status(self, checkout_request_id: str) -> dict: ...


class MockPaymentProvider:
    name = "mock"

    def initiate_stk_push(self, *, amount_kes: int, phone_number: str, account_reference: str, description: str) -> InitiationResult:
        del amount_kes, phone_number, account_reference, description
        key = secrets.token_hex(12)
        return InitiationResult(f"MOCK-MERCHANT-{key}", f"MOCK-CHECKOUT-{key}", "Mock request created; no M-PESA transaction was sent.")

    def query_stk_status(self, checkout_request_id: str) -> dict:
        return {"provider": "mock", "checkout_request_id": checkout_request_id, "status": "PENDING", "actual_mpesa_transaction": False}


class DarajaPaymentProvider:
    name = "daraja"

    def __init__(self):
        self.base_url = "https://api.safaricom.co.ke" if settings.mpesa_environment == "production" else "https://sandbox.safaricom.co.ke"
        self._token: str | None = None
        self._token_expiry = datetime.min.replace(tzinfo=timezone.utc)
        self._lock = Lock()

    def _credentials(self) -> tuple[str, str, str, str, str]:
        key = settings.mpesa_consumer_key.strip()
        secret = settings.mpesa_consumer_secret.strip()
        shortcode = settings.mpesa_shortcode.strip()
        passkey = settings.mpesa_passkey.strip()
        callback = settings.mpesa_callback_url.strip()
        if not all((key, secret, shortcode, passkey, callback)):
            raise PaymentProviderError("Daraja credentials and callback URL are not configured")
        if settings.mpesa_environment == "production" and not callback.startswith("https://"):
            raise PaymentProviderError("Production Daraja callback URL must use HTTPS")
        return key, secret, shortcode, passkey, callback

    def _access_token(self) -> str:
        key, secret, _, _, _ = self._credentials()
        now = datetime.now(timezone.utc)
        with self._lock:
            if self._token and now < self._token_expiry:
                return self._token
            basic = base64.b64encode(f"{key}:{secret}".encode()).decode()
            try:
                response = httpx.get(
                    f"{self.base_url}/oauth/v1/generate",
                    params={"grant_type": "client_credentials"},
                    headers={"Authorization": f"Basic {basic}"},
                    timeout=15.0,
                )
                response.raise_for_status()
                payload = response.json()
                token = payload["access_token"]
                expires = max(30, int(payload.get("expires_in", 3600)))
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                raise PaymentProviderError("Could not obtain a Daraja access token") from exc
            self._token = token
            self._token_expiry = now + timedelta(seconds=expires - min(60, expires // 5))
            return token

    @staticmethod
    def _timestamp() -> str:
        # Kenya observes UTC+3 year round; Daraja uses YYYYMMDDHHMMSS.
        nairobi = timezone(timedelta(hours=3))
        return datetime.now(nairobi).strftime("%Y%m%d%H%M%S")

    def _password(self, shortcode: str, passkey: str, timestamp: str) -> str:
        return base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode()

    def initiate_stk_push(self, *, amount_kes: int, phone_number: str, account_reference: str, description: str) -> InitiationResult:
        _, _, shortcode, passkey, callback = self._credentials()
        timestamp = self._timestamp()
        body = {
            "BusinessShortCode": shortcode,
            "Password": self._password(shortcode, passkey, timestamp),
            "Timestamp": timestamp,
            "TransactionType": settings.mpesa_transaction_type,
            "Amount": amount_kes,
            "PartyA": phone_number,
            "PartyB": shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": callback,
            "AccountReference": account_reference[:12],
            "TransactionDesc": description[:100],
        }
        try:
            response = httpx.post(
                f"{self.base_url}/mpesa/stkpush/v1/processrequest",
                json=body,
                headers={"Authorization": f"Bearer {self._access_token()}"},
                timeout=20.0,
            )
            response.raise_for_status()
            payload = response.json()
            if str(payload.get("ResponseCode")) != "0":
                raise PaymentProviderError("Daraja rejected the STK Push request")
            return InitiationResult(
                merchant_request_id=str(payload["MerchantRequestID"]),
                checkout_request_id=str(payload["CheckoutRequestID"]),
                response_description=str(payload.get("ResponseDescription", "STK Push accepted")),
            )
        except PaymentProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise PaymentProviderError("Daraja STK Push request failed") from exc

    def query_stk_status(self, checkout_request_id: str) -> dict:
        _, _, shortcode, passkey, _ = self._credentials()
        timestamp = self._timestamp()
        body = {
            "BusinessShortCode": shortcode,
            "Password": self._password(shortcode, passkey, timestamp),
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }
        try:
            response = httpx.post(
                f"{self.base_url}/mpesa/stkpushquery/v1/query",
                json=body,
                headers={"Authorization": f"Bearer {self._access_token()}"},
                timeout=20.0,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PaymentProviderError("Daraja STK status query failed") from exc


def get_payment_provider() -> PaymentProvider:
    if settings.payment_provider == "daraja":
        return DarajaPaymentProvider()
    return MockPaymentProvider()
