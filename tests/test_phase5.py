from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.dependencies import (
    escrow_provider,
    get_current_user,
    get_escrow_repository,
    get_ledger_repository,
    get_order_repository,
    get_payment_repository,
    payment_provider,
)
from app.main import app
from app.models.escrow import CustodyStatus, EscrowStatus
from app.models.order import OrderStatus, PaymentStatus
from app.models.user import UserRole
from app.schemas.user import UserPublic
from app.services.escrow_providers import MockEscrowProvider, ReleaseResult
from app.services.payment_providers import InitiationResult, MockPaymentProvider

FARMER_ID = "64b000000000000000000001"
BUYER_ID = "64b000000000000000000003"
OTHER_BUYER_ID = "64b000000000000000000004"
ORDER_ID = "64b000000000000000000010"


def user(user_id=BUYER_ID, role=UserRole.BUYER):
    now = datetime.now(timezone.utc)
    return UserPublic(id=user_id, full_name="Test User", email="test@example.test", phone="+254712345678", role=role, is_active=True, created_at=now, updated_at=now)


class MemoryOrders:
    def __init__(self):
        self.items = {ORDER_ID: {
            "id": ORDER_ID, "buyer_id": BUYER_ID, "seller_id": FARMER_ID,
            "product_id": "64b000000000000000000099", "product_name": "Maize",
            "quantity": 10, "unit": "kg", "unit_price_kes": 60,
            "total_amount_kes": 600, "delivery_information": {
                "recipient_name": "Buyer", "recipient_phone": "254712345678", "county": "Nairobi",
                "sub_county": "Westlands", "location": "Westlands", "instructions": None,
            }, "payment_status": "UNPAID", "order_status": "AWAITING_PAYMENT",
            "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
        }}
        self.lock = Lock()

    def get(self, order_id):
        item = self.items.get(order_id)
        return deepcopy(item) if item else None

    def mark_paid(self, order_id, payment_id):
        with self.lock:
            item = self.items.get(order_id)
            if item and item["order_status"] == "AWAITING_PAYMENT" and item["payment_status"] == "UNPAID":
                item["order_status"] = "PAID"
                item["payment_status"] = "PAID"
                item["payment_id"] = payment_id
                return deepcopy(item)
            if item and item.get("payment_id") == payment_id and item["payment_status"] == "PAID":
                return deepcopy(item)
            return None


class MemoryPayments:
    def __init__(self):
        self.items = {}
        self.lock = Lock()

    @staticmethod
    def public(doc):
        if doc is None:
            return None
        result = deepcopy(doc)
        for field in ("active_order_id", "idempotency_key", "merchant_request_id", "callback_phone_number", "callback_amount_kes"):
            result.pop(field, None)
        return result

    def create_pending(self, values):
        with self.lock:
            prior = next((p for p in self.items.values() if p["idempotency_key"] == values["idempotency_key"]), None)
            if prior:
                if all(prior[k] == values[k] for k in ("order_id", "amount_kes", "phone_number")):
                    return self.public(prior)
                raise ValueError("idempotency conflict")
            if any(p["order_id"] == values["order_id"] and p["status"] in {"PENDING", "INITIATING", "INITIATED"} for p in self.items.values()):
                raise ValueError("active order payment")
            now = datetime.now(timezone.utc)
            doc = {**deepcopy(values), "id": str(ObjectId()), "status": "PENDING", "currency": "KES", "created_at": now, "updated_at": now, "checkout_request_id": None, "provider_receipt": None}
            self.items[doc["id"]] = doc
            return self.public(doc)

    def get(self, payment_id):
        doc = self.items.get(payment_id)
        return self.public(doc)

    def get_by_checkout(self, checkout_request_id):
        doc = next((p for p in self.items.values() if p.get("checkout_request_id") == checkout_request_id), None)
        return self.public(doc)

    def get_by_idempotency(self, key):
        doc = next((p for p in self.items.values() if p["idempotency_key"] == key), None)
        return self.public(doc)

    def claim_initiation(self, payment_id):
        with self.lock:
            doc = self.items.get(payment_id)
            if not doc or doc["status"] != "PENDING":
                return None
            doc["status"] = "INITIATING"
            return self.public(doc)

    def set_initiated(self, payment_id, merchant_request_id, checkout_request_id):
        with self.lock:
            doc = self.items[payment_id]
            if doc["status"] != "INITIATING":
                return None
            doc.update(status="INITIATED", merchant_request_id=merchant_request_id, checkout_request_id=checkout_request_id)
            return self.public(doc)

    def set_initiation_failed(self, payment_id, reason):
        self.items[payment_id].update(status="INITIATION_FAILED", failure_reason=reason)

    def complete_callback(self, payment_id, *, status, receipt, callback_amount, callback_phone, failure_reason=None):
        with self.lock:
            doc = self.items[payment_id]
            proposed = (status.value, receipt, callback_amount, callback_phone)
            if doc["status"] not in {"INITIATING", "INITIATED"}:
                current = (doc["status"], doc.get("provider_receipt"), doc.get("callback_amount_kes"), doc.get("callback_phone_number"))
                if current == proposed:
                    return self.public(doc)
                from app.repositories.payment_repository import PaymentConflictError
                raise PaymentConflictError
            doc.update(status=status.value, provider_receipt=receipt, callback_amount_kes=callback_amount, callback_phone_number=callback_phone, failure_reason=failure_reason, updated_at=datetime.now(timezone.utc))
            return self.public(doc)

    def list_for_buyer(self, buyer_id, *, skip, limit):
        docs = [p for p in self.items.values() if p["buyer_id"] == buyer_id]
        return [self.public(p) for p in docs[skip:skip + limit]], len(docs)

    def list_all(self, *, skip, limit):
        docs = list(self.items.values())
        return [self.public(p) for p in docs[skip:skip + limit]], len(docs)


class MemoryEscrows:
    def __init__(self):
        self.items = {}
        self.unresolved = set()
        self.lock = Lock()

    def get(self, escrow_id):
        doc = self.items.get(escrow_id)
        return deepcopy(doc) if doc else None

    def get_by_order(self, order_id):
        doc = next((e for e in self.items.values() if e["order_id"] == order_id), None)
        return deepcopy(doc) if doc else None

    def create_for_payment(self, values):
        old = self.get_by_order(values["order_id"])
        if old:
            return old
        now = datetime.now(timezone.utc)
        doc = {**deepcopy(values), "id": str(ObjectId()), "status": "PAYMENT_RECEIVED", "custody_status": "NOT_SAFEGUARDED", "actual_funds_safeguarded": False, "created_at": now, "updated_at": now}
        self.items[doc["id"]] = doc
        return deepcopy(doc)

    def transition(self, escrow_id, allowed, target, changes=None):
        with self.lock:
            doc = self.items.get(escrow_id)
            if not doc or doc["status"] not in allowed:
                return None
            doc.update(deepcopy(changes or {}), status=target, updated_at=datetime.now(timezone.utc))
            return deepcopy(doc)

    def has_unresolved_dispute(self, order_id):
        return order_id in self.unresolved


class MemoryLedger:
    def __init__(self):
        self.items = {}

    def append(self, event):
        key = event["event_key"]
        if key in self.items:
            old = self.items[key]
            assert all(old[k] == event[k] for k in ("event_type", "amount_kes", "status", "order_id", "payment_id"))
            return deepcopy(old)
        doc = {**deepcopy(event), "id": str(ObjectId()), "currency": "KES", "timestamp": datetime.now(timezone.utc)}
        self.items[key] = doc
        return deepcopy(doc)

    def list_for_order(self, order_id):
        return [deepcopy(e) for e in self.items.values() if e["order_id"] == order_id]


class DarajaFake:
    name = "daraja"

    def __init__(self, result_code=0):
        self.result_code = result_code
        self.initiations = 0

    def initiate_stk_push(self, **kwargs):
        self.initiations += 1
        return InitiationResult("merchant-123", "ws_CO_checkout123", "Accepted")

    def query_stk_status(self, checkout_request_id):
        return {"CheckoutRequestID": checkout_request_id, "ResponseCode": "0", "ResultCode": str(self.result_code)}


@pytest.fixture
def phase5_client(monkeypatch):
    orders, payments, escrows, ledger = MemoryOrders(), MemoryPayments(), MemoryEscrows(), MemoryLedger()
    current = {"user": user()}
    mpesa = MockPaymentProvider()
    safekeep = MockEscrowProvider()
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "payment_provider", "mock")
    monkeypatch.setattr(settings, "escrow_provider", "mock")
    app.dependency_overrides[get_order_repository] = lambda: orders
    app.dependency_overrides[get_payment_repository] = lambda: payments
    app.dependency_overrides[get_escrow_repository] = lambda: escrows
    app.dependency_overrides[get_ledger_repository] = lambda: ledger
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    app.dependency_overrides[payment_provider] = lambda: mpesa
    app.dependency_overrides[escrow_provider] = lambda: safekeep
    with TestClient(app) as client:
        yield client, current, orders, payments, escrows, ledger, mpesa, safekeep
    app.dependency_overrides.clear()


def initiate(client, order_id=ORDER_ID, idempotency="phase5-idempotency-key-001"):
    return client.post("/payments/initiate", headers={"Idempotency-Key": idempotency}, json={"order_id": order_id, "phone_number": "0712345678"})


def test_payment_initiation_does_not_mark_order_paid_and_is_idempotent(phase5_client):
    client, _, orders, payments, _, _, provider, _ = phase5_client
    first = initiate(client)
    assert first.status_code == 201
    payment = first.json()
    assert payment["status"] == "INITIATED" and payment["provider"] == "mock"
    assert orders.get(ORDER_ID)["payment_status"] == "UNPAID"
    assert orders.get(ORDER_ID)["order_status"] == "AWAITING_PAYMENT"
    again = initiate(client)
    assert again.status_code == 201 and again.json()["id"] == payment["id"]
    assert provider.name == "mock" and len(payments.items) == 1


def test_mock_confirmation_marks_payment_paid_creates_internal_escrow_and_ledger_once(phase5_client):
    client, _, orders, _, escrows, ledger, _, _ = phase5_client
    payment = initiate(client).json()
    url = f"/payments/mock/{payment['id']}/callback"
    success = client.post(url, json={"success": True})
    assert success.status_code == 200 and success.json()["status"] == "SUCCEEDED"
    assert orders.get(ORDER_ID)["order_status"] == "PAID"
    retrieved_order = client.get(f"/orders/{ORDER_ID}")
    assert retrieved_order.status_code == 200
    assert retrieved_order.json()["payment_id"] == payment["id"]
    escrow = escrows.get_by_order(ORDER_ID)
    assert escrow["amount_kes"] == 600
    assert escrow["commission_kes"] == 30
    assert escrow["seller_amount_kes"] == 570
    assert escrow["custody_status"] == CustodyStatus.NOT_SAFEGUARDED.value
    assert escrow["actual_funds_safeguarded"] is False
    assert client.post(url, json={"success": True}).status_code == 200
    assert len(ledger.items) == 1


def test_mock_rejects_wrong_amount_and_failed_payment_never_marks_order_paid(phase5_client):
    client, _, orders, _, _, ledger, _, _ = phase5_client
    payment = initiate(client).json()
    mismatch = client.post(f"/payments/mock/{payment['id']}/callback", json={"success": True, "amount_kes": 599})
    assert mismatch.status_code == 409
    assert orders.get(ORDER_ID)["payment_status"] == "UNPAID"
    failed = client.post(f"/payments/mock/{payment['id']}/callback", json={"success": False})
    assert failed.status_code == 200 and failed.json()["status"] == "FAILED"
    assert orders.get(ORDER_ID)["order_status"] == "AWAITING_PAYMENT"
    assert [x["status"] for x in ledger.items.values()] == ["MOCK_FAILED"]


def test_daraja_callback_requires_query_and_exact_callback_amount_and_phone(phase5_client, monkeypatch):
    client, _, orders, _, escrows, ledger, _, safekeep = phase5_client
    provider = DarajaFake()
    app.dependency_overrides[payment_provider] = lambda: provider
    monkeypatch.setattr(settings, "payment_provider", "daraja")
    payment = client.post("/payments/initiate", headers={"Idempotency-Key":"daraja-idempotency-0001"}, json={"order_id":ORDER_ID,"phone_number":"0712345678"}).json()
    callback = {"Body":{"stkCallback":{
        "CheckoutRequestID":payment["checkout_request_id"], "ResultCode":0, "ResultDesc":"Success",
        "CallbackMetadata":{"Item":[{"Name":"Amount","Value":600},{"Name":"MpesaReceiptNumber","Value":"QWE1234567"},{"Name":"PhoneNumber","Value":254712345678}]}
    }}}
    wrong = deepcopy(callback)
    wrong["Body"]["stkCallback"]["CallbackMetadata"]["Item"][0]["Value"] = 599
    assert client.post("/payments/callback/daraja", json=wrong).status_code == 503
    wrong_phone = deepcopy(callback)
    wrong_phone["Body"]["stkCallback"]["CallbackMetadata"]["Item"][2]["Value"] = 254722222222
    assert client.post("/payments/callback/daraja", json=wrong_phone).status_code == 503
    assert orders.get(ORDER_ID)["payment_status"] == "UNPAID"
    response = client.post("/payments/callback/daraja", json=callback)
    assert response.status_code == 200
    assert orders.get(ORDER_ID)["payment_status"] == "PAID"
    assert provider.initiations == 1
    assert any(e["event_type"] == "PAYMENT_RECEIVED" and e["status"] == "CONFIRMED" for e in ledger.items.values())
    assert escrows.get_by_order(ORDER_ID)["actual_funds_safeguarded"] is False


def test_daraja_failure_callback_must_match_provider_query(phase5_client, monkeypatch):
    client, _, orders, _, _, _, _, _ = phase5_client
    provider = DarajaFake(result_code=1)
    app.dependency_overrides[payment_provider] = lambda: provider
    monkeypatch.setattr(settings, "payment_provider", "daraja")
    payment = client.post("/payments/initiate", headers={"Idempotency-Key":"daraja-idempotency-0002"}, json={"order_id":ORDER_ID,"phone_number":"0712345678"}).json()
    callback = {"Body":{"stkCallback":{"CheckoutRequestID":payment["checkout_request_id"],"ResultCode":1,"ResultDesc":"Cancelled"}}}
    assert client.post("/payments/callback/daraja", json=callback).status_code == 200
    assert orders.get(ORDER_ID)["payment_status"] == "UNPAID"
    provider.result_code = 0
    payment2 = client.post("/payments/initiate", headers={"Idempotency-Key":"daraja-idempotency-0003"}, json={"order_id":ORDER_ID,"phone_number":"0712345678"})
    # The first failed callback releases the active-order payment lock, so a new payment may be started.
    assert payment2.status_code == 201


def test_payment_access_is_private_and_mock_simulation_is_development_only(phase5_client, monkeypatch):
    client, current, _, _, _, _, _, _ = phase5_client
    payment = initiate(client).json()
    current["user"] = user(OTHER_BUYER_ID)
    assert client.get(f"/payments/{payment['id']}").status_code == 404
    assert client.post(f"/payments/mock/{payment['id']}/callback", json={"success":True}).status_code == 404
    monkeypatch.setattr(settings, "app_env", "production")
    current["user"] = user()
    assert client.post(f"/payments/mock/{payment['id']}/callback", json={"success":True}).status_code == 404
    assert initiate(client, idempotency="prod-mock-disabled-key").status_code == 503


def test_escrow_release_waits_for_delivery_and_disputes_then_simulates_once(phase5_client):
    client, current, orders, _, escrows, ledger, _, _ = phase5_client
    payment = initiate(client).json()
    client.post(f"/payments/mock/{payment['id']}/callback", json={"success":True})
    escrow = escrows.get_by_order(ORDER_ID)
    current["user"] = user(FARMER_ID, UserRole.FARMER)
    release_url = f"/escrow/{escrow['id']}/release"
    assert client.post(release_url).status_code == 409
    orders.items[ORDER_ID]["order_status"] = OrderStatus.COMPLETED.value
    escrows.unresolved.add(ORDER_ID)
    assert client.post(release_url).status_code == 409
    escrows.unresolved.clear()
    released = client.post(release_url)
    assert released.status_code == 200
    assert released.json()["escrow"]["status"] == EscrowStatus.SIMULATED_SETTLEMENT.value
    assert released.json()["escrow"]["actual_funds_safeguarded"] is False
    duplicate = client.post(release_url)
    assert duplicate.status_code == 200
    events = [e["event_type"] for e in ledger.items.values()]
    assert events.count("MOCK_SETTLEMENT_SIMULATED") == 1
    assert "SELLER_PAYOUT_CONFIRMED" not in events


def test_buyer_refund_request_is_recorded_but_not_claimed_as_paid(phase5_client):
    client, current, _, _, escrows, ledger, _, _ = phase5_client
    payment = initiate(client).json()
    client.post(f"/payments/mock/{payment['id']}/callback", json={"success":True})
    escrow = escrows.get_by_order(ORDER_ID)
    response = client.post(f"/escrow/{escrow['id']}/refund-request", json={"reason":"Product quality concern; please review."})
    assert response.status_code == 200
    assert response.json()["escrow"]["status"] == EscrowStatus.REFUND_REQUESTED.value
    assert "no real refund" in response.json()["message"].lower()
    current["user"] = user(FARMER_ID, UserRole.FARMER)
    assert client.post(f"/escrow/{escrow['id']}/refund-request", json={"reason":"not allowed"}).status_code == 403
    assert any(e["event_type"] == "REFUND_REQUESTED" for e in ledger.items.values())


def test_provider_payout_failure_is_recorded_then_retry_confirms_payout(phase5_client):
    client, current, orders, _, escrows, ledger, _, _ = phase5_client
    payment = initiate(client).json()
    client.post(f"/payments/mock/{payment['id']}/callback", json={"success":True})
    escrow = escrows.get_by_order(ORDER_ID)
    orders.items[ORDER_ID]["order_status"] = OrderStatus.COMPLETED.value
    escrows.items[escrow["id"]]["actual_funds_safeguarded"] = True
    current["user"] = user(FARMER_ID, UserRole.FARMER)

    class Partner:
        name = "partner"
        fail = True

        def release(self, **kwargs):
            if self.fail:
                from app.services.escrow_providers import EscrowProviderError
                raise EscrowProviderError("provider error")
            return ReleaseResult(False, True, "PARTNER-SETTLEMENT-001")

    partner = Partner()
    app.dependency_overrides[escrow_provider] = lambda: partner
    url = f"/escrow/{escrow['id']}/release"
    assert client.post(url).status_code == 503
    assert escrows.get(escrow["id"])["status"] == EscrowStatus.SETTLEMENT_FAILED.value
    assert any(e["event_type"] == "SELLER_PAYOUT_FAILED" for e in ledger.items.values())
    partner.fail = False
    settled = client.post(url)
    assert settled.status_code == 200
    assert settled.json()["escrow"]["status"] == EscrowStatus.SETTLED.value
    events = [e["event_type"] for e in ledger.items.values()]
    assert "SELLER_PAYOUT_CONFIRMED" in events
    assert "PLATFORM_COMMISSION_RECORDED" in events


def test_daraja_production_uses_safaricom_urls_and_never_logs_credentials(monkeypatch):
    import app.services.payment_providers as adapters

    monkeypatch.setattr(settings, "mpesa_environment", "production")
    monkeypatch.setattr(settings, "mpesa_consumer_key", "test-consumer-key")
    monkeypatch.setattr(settings, "mpesa_consumer_secret", "test-consumer-secret")
    monkeypatch.setattr(settings, "mpesa_shortcode", "123456")
    monkeypatch.setattr(settings, "mpesa_passkey", "test-passkey")
    monkeypatch.setattr(settings, "mpesa_callback_url", "https://example.test/payments/callback/daraja")
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    def fake_get(url, **kwargs):
        calls.append(("GET", url, kwargs))
        return Response({"access_token": "safe-test-token", "expires_in": 3600})

    def fake_post(url, **kwargs):
        calls.append(("POST", url, kwargs))
        if url.endswith("/mpesa/stkpush/v1/processrequest"):
            return Response({"ResponseCode": "0", "MerchantRequestID": "merchant-id", "CheckoutRequestID": "checkout-id", "ResponseDescription": "Accepted"})
        return Response({"ResponseCode": "0", "ResponseDescription": "Success", "ResultCode": "0", "CheckoutRequestID": "checkout-id"})

    monkeypatch.setattr(adapters.httpx, "get", fake_get)
    monkeypatch.setattr(adapters.httpx, "post", fake_post)
    provider = adapters.DarajaPaymentProvider()
    initiated = provider.initiate_stk_push(amount_kes=600, phone_number="254712345678", account_reference="ORD-0000000010", description="Agriculture order")
    assert initiated.checkout_request_id == "checkout-id"
    assert provider.query_stk_status("checkout-id")["ResultCode"] == "0"
    assert calls[0][1] == "https://api.safaricom.co.ke/oauth/v1/generate"
    assert calls[1][1] == "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    assert calls[2][1] == "https://api.safaricom.co.ke/mpesa/stkpushquery/v1/query"
    assert calls[1][2]["json"]["Amount"] == 600
    assert calls[1][2]["json"]["PhoneNumber"] == "254712345678"
    assert "test-consumer-secret" not in repr(calls)
    assert "test-passkey" not in repr(calls)
