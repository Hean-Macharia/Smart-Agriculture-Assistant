from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.core.dependencies import (
    get_current_user,
    get_farm_repository,
    get_market_price_repository,
    get_notification_repository,
    get_sms_preferences_repository,
    get_user_repository,
    sms_provider,
)
from app.main import app
from app.models.notification import NotificationStatus
from app.schemas.user import UserPublic
from app.services.notification_service import NotificationConsentRequiredError, send_notification
from app.services.sms_providers import SmsResult
from app.core.config import Settings
from pydantic import ValidationError
from app.services.ussd_service import MockUssdProvider, UssdRequest

USER_ID = "64b000000000000000000021"
PHONE = "+254712345678"


def public_user():
    now = datetime.now(timezone.utc)
    return UserPublic(id=USER_ID, full_name="Test Farmer", email="farmer@example.test", phone=PHONE, role="FARMER", is_active=True, created_at=now, updated_at=now)


class MemoryPreferences:
    def __init__(self, consented=False, language="en", categories=None):
        self.consented = consented
        self.language = language
        self.categories = categories or []
        self.accepted = set()
        self.phone_state = {}

    def get_for_user(self, user_id, phone):
        return {"phone_number": phone, "consented": self.consented, "language": self.language, "categories": self.categories, "phone_verified": getattr(self, "verified", False), "consented_at": None, "opted_out_at": None, "consent_history": []}

    def save_for_user(self, **kwargs):
        self.consented = kwargs["consented"]
        self.language = kwargs["language"]
        self.categories = kwargs["categories"]
        return self.get_for_user(kwargs["user_id"], kwargs["phone_number"])

    def get_for_phone(self, phone):
        return self.phone_state.get(phone)

    def set_phone_consent(self, *, phone_number, consented, source):
        self.phone_state[phone_number] = {"phone_number": phone_number, "consented": consented, "language": "en", "phone_verified": consented and source == "inbound_sms"}
        return self.phone_state[phone_number]

    def set_phone_language(self, *, phone_number, language, source):
        self.phone_state.setdefault(phone_number, {"phone_number": phone_number, "consented": False})["language"] = language

    def accept_inbound(self, *, provider_message_id, phone_number, command, hourly_limit):
        if provider_message_id in self.accepted:
            return False
        self.accepted.add(provider_message_id)
        return True


class MemoryUsers:
    def get_by_id(self, user_id):
        return {"_id": USER_ID, "phone": PHONE, "is_active": True} if user_id == USER_ID else None

    def get_by_phone(self, phone):
        return {"_id": USER_ID} if phone == PHONE else None


class MemoryNotifications:
    def __init__(self):
        self.items = {}

    def create_pending(self, values):
        item = {**values, "id": "notification-id", "status": "PENDING", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc), "provider_reference": None}
        self.items[item["id"]] = item
        return deepcopy(item), True

    def claim(self, notification_id):
        self.items[notification_id]["status"] = "SENDING"
        return deepcopy(self.items[notification_id])

    def finish(self, notification_id, *, status, provider_reference):
        self.items[notification_id].update(status=status, provider_reference=provider_reference)
        return deepcopy(self.items[notification_id])

    def get(self, notification_id):
        return deepcopy(self.items.get(notification_id))

    def update_delivery_receipt(self, provider_reference, status):
        return None


class MemoryProvider:
    name = "test_sms"

    def __init__(self):
        self.calls = []

    def send_sms(self, *, to, message, idempotency_key):
        self.calls.append((to, message, idempotency_key))
        return SmsResult(False, "provider-message-1")


def test_outbound_sms_requires_explicit_consent_and_respects_kiswahili_template():
    prefs = MemoryPreferences()
    provider = MemoryProvider()
    users, notifications = MemoryUsers(), MemoryNotifications()
    with pytest.raises(NotificationConsentRequiredError):
        send_notification(recipient_user_id=USER_ID, event="PAYMENT_CONFIRMATION", message="secret payment data", idempotency_key="test-sms-0001", users=users, notifications=notifications, preferences=prefs, provider=provider)
    assert provider.calls == []

    prefs.consented = True
    prefs.verified = True
    prefs.language = "sw"
    prefs.categories = ["PAYMENT_CONFIRMATION"]
    outcome = send_notification(recipient_user_id=USER_ID, event="PAYMENT_CONFIRMATION", message="Sensitive amount should not be sent", idempotency_key="test-sms-0002", users=users, notifications=notifications, preferences=prefs, provider=provider)
    assert outcome.notification["status"] == NotificationStatus.ACCEPTED.value
    assert "taarifa ya malipo" in provider.calls[0][1]
    assert "Sensitive amount" not in provider.calls[0][1]


@pytest.fixture
def sms_client(monkeypatch):
    prefs, provider, notifications = MemoryPreferences(), MemoryProvider(), MemoryNotifications()
    users = MemoryUsers()
    app.dependency_overrides[get_current_user] = public_user
    app.dependency_overrides[get_sms_preferences_repository] = lambda: prefs
    app.dependency_overrides[get_notification_repository] = lambda: notifications
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides[get_farm_repository] = lambda: object()
    app.dependency_overrides[get_market_price_repository] = lambda: object()
    app.dependency_overrides[sms_provider] = lambda: provider
    monkeypatch.setattr(config.settings, "sms_webhook_secret", "sms-test-webhook-secret-is-long-123456")
    monkeypatch.setattr(config.settings, "sms_inbound_hourly_limit", 8)
    with TestClient(app) as client:
        yield client, prefs, provider, notifications
    app.dependency_overrides.clear()


def test_preferences_are_authenticated_and_opt_in_is_explicit(sms_client):
    client, prefs, _, _ = sms_client
    before = client.get("/notifications/preferences")
    assert before.status_code == 200
    assert before.json()["consented"] is False
    updated = client.put("/notifications/preferences", json={"consented": True, "language": "sw", "categories": ["WEATHER_ALERT", "MARKET_PRICE"]})
    assert updated.status_code == 200
    assert updated.json()["consented"] is True
    assert updated.json()["phone_number"] == PHONE
    assert updated.json()["phone_verified"] is False
    assert prefs.categories == ["WEATHER_ALERT", "MARKET_PRICE"]


def test_inbound_commands_require_secret_are_idempotent_and_support_opt_out(sms_client):
    client, prefs, provider, _ = sms_client
    data = {"from": "0712345678", "text": "HELP", "id": "provider-msg-100"}
    assert client.post("/notifications/inbound/africas-talking", data=data).status_code == 401
    headers = {"X-SMS-Webhook-Token": "sms-test-webhook-secret-is-long-123456"}
    help_response = client.post("/notifications/inbound/africas-talking", data=data, headers=headers)
    assert help_response.status_code == 200 and help_response.json()["status"] == "accepted"
    assert "Commands" in provider.calls[0][1]
    replay = client.post("/notifications/inbound/africas-talking", data=data, headers=headers)
    assert replay.status_code == 200 and replay.json()["status"] == "duplicate_or_rate_limited"
    stop = client.post("/notifications/inbound/africas-talking", data={**data, "text": "STOP", "id": "provider-msg-101"}, headers=headers)
    assert stop.status_code == 200
    assert prefs.phone_state[PHONE]["consented"] is False
    start = client.post("/notifications/inbound/africas-talking", data={**data, "text": "START", "id": "provider-msg-102"}, headers=headers)
    assert start.status_code == 200
    assert prefs.phone_state[PHONE]["consented"] is True
    assert prefs.phone_state[PHONE]["phone_verified"] is True


def test_delivery_receipt_requires_valid_hmac(sms_client):
    import hashlib
    import hmac
    import json

    client, _, _, _ = sms_client
    raw = json.dumps({"message_id": "provider-message-1", "status": "DELIVERED"}).encode()
    signature = hmac.new(b"sms-test-webhook-secret-is-long-123456", raw, hashlib.sha256).hexdigest()
    response = client.post("/notifications/callback/delivery", content=raw, headers={"Content-Type": "application/json", "X-SMS-Signature": signature})
    assert response.status_code == 404
    rejected = client.post("/notifications/callback/delivery", content=raw, headers={"Content-Type": "application/json", "X-SMS-Signature": "invalid"})
    assert rejected.status_code == 401


def test_sms_environment_separation_rejects_production_in_development():
    with pytest.raises(ValidationError, match="SMS_ENVIRONMENT=production requires APP_ENV=production"):
        Settings(_env_file=None, app_env="development", payment_provider="mock", sms_provider="africas_talking", sms_environment="production", sms_production_api_key="production-only-key", sms_production_username="prod-app")


def test_ussd_mock_menu_is_explicitly_not_live():
    response = MockUssdProvider().respond(UssdRequest("session-1", PHONE, "", "sw"))
    assert response.startswith("CON")
    assert "Hali ya hewa" in response


def test_ussd_mock_endpoint_is_dev_only_and_labels_simulation(monkeypatch):
    monkeypatch.setattr(config.settings, "app_env", "test")
    with TestClient(app) as client:
        response = client.post("/ussd/mock/session", json={
            "session_id": "demo-session",
            "phone_number": "0712345678",
            "text": "",
            "language": "sw",
        })
        assert response.status_code == 200
        assert response.json()["provider"] == "mock_ussd"
        assert response.json()["live_gateway_connected"] is False
        assert response.json()["response"].startswith("CON")

        monkeypatch.setattr(config.settings, "app_env", "production")
        hidden = client.post("/ussd/mock/session", json={"session_id": "demo-session", "phone_number": PHONE})
        assert hidden.status_code == 404
