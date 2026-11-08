from copy import deepcopy
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.dependencies import escrow_provider, get_current_user, get_delivery_repository, get_dispute_repository, get_escrow_repository, get_ledger_repository, get_order_repository
from app.main import app
from app.models.order import OrderStatus, PaymentStatus
from app.models.user import UserRole
from app.schemas.user import UserPublic
from app.services.escrow_providers import MockEscrowProvider

SELLER = "64b000000000000000000001"
BUYER = "64b000000000000000000003"
ADMIN = "64b000000000000000000005"
ORDER = "64b000000000000000000010"


def public_user(uid, role):
    now = datetime.now(timezone.utc)
    return UserPublic(id=uid, full_name="Test User", email="test@example.test", phone="0712345678", role=role, is_active=True, created_at=now, updated_at=now)


class MemoryOrders:
    def __init__(self):
        self.order = {"id": ORDER, "buyer_id": BUYER, "seller_id": SELLER, "payment_status": PaymentStatus.PAID.value, "order_status": OrderStatus.READY_FOR_DELIVERY.value}

    def get(self, order_id):
        return deepcopy(self.order) if order_id == ORDER else None

    def transition(self, order_id, allowed, target):
        if order_id != ORDER or self.order["order_status"] not in allowed:
            return None
        self.order["order_status"] = target
        return deepcopy(self.order)


class MemoryDeliveries:
    def __init__(self):
        self.items = {}

    def create(self, values):
        now = datetime.now(timezone.utc)
        doc = {**deepcopy(values), "id": str(ObjectId()), "status": "PENDING", "events": [{"status": "PENDING", "at": now, "by": values["seller_id"], "note": "Delivery created"}], "created_at": now, "updated_at": now}
        self.items[doc["id"]] = doc
        return deepcopy(doc)

    def get(self, delivery_id):
        return deepcopy(self.items.get(delivery_id))

    def list_for_user(self, field, user_id, *, skip, limit):
        docs = [d for d in self.items.values() if d[field] == user_id]
        return deepcopy(docs[skip:skip + limit]), len(docs)

    def transition(self, delivery_id, allowed, target, actor_id, note):
        doc = self.items.get(delivery_id)
        if not doc or doc["status"] not in allowed:
            return None
        now = datetime.now(timezone.utc)
        doc.update(status=target, updated_at=now)
        doc["events"].append({"status": target, "at": now, "by": actor_id, "note": note})
        return deepcopy(doc)


class MemoryDisputes:
    def __init__(self):
        self.items = {}

    def create(self, values):
        if any(d["order_id"] == values["order_id"] for d in self.items.values()):
            raise ValueError("A dispute already exists for this order")
        now = datetime.now(timezone.utc)
        doc = {**deepcopy(values), "id": str(ObjectId()), "status": "OPEN", "decisions": [], "created_at": now, "updated_at": now}
        self.items[doc["id"]] = doc
        return deepcopy(doc)

    def get(self, dispute_id):
        return deepcopy(self.items.get(dispute_id))

    def list_for_user(self, user_id, *, skip, limit):
        docs = [d for d in self.items.values() if user_id in (d["buyer_id"], d["seller_id"])]
        return deepcopy(docs[skip:skip + limit]), len(docs)

    def list_all(self, *, skip, limit):
        docs = list(self.items.values())
        return deepcopy(docs[skip:skip + limit]), len(docs)

    def review(self, dispute_id, *, status, admin_id, resolution, decision, allowed_current=None):
        doc = self.items.get(dispute_id)
        if not doc or doc["status"] not in set(allowed_current or {"OPEN", "UNDER_REVIEW"}):
            return None
        now = datetime.now(timezone.utc)
        doc.update(status=status, updated_at=now)
        doc["decisions"].append({"admin_id": admin_id, "status": status, "decision": decision, "resolution": resolution, "at": now})
        return deepcopy(doc)


@pytest.fixture
def phase6_client():
    orders, deliveries, disputes = MemoryOrders(), MemoryDeliveries(), MemoryDisputes()
    current = {"user": public_user(SELLER, UserRole.FARMER)}
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    app.dependency_overrides[get_order_repository] = lambda: orders
    app.dependency_overrides[get_delivery_repository] = lambda: deliveries
    app.dependency_overrides[get_dispute_repository] = lambda: disputes
    with TestClient(app) as client:
        yield client, current, orders, deliveries, disputes
    app.dependency_overrides.clear()


def test_delivery_lifecycle_authorizes_seller_and_buyer_confirmation(phase6_client):
    client, current, orders, deliveries, _ = phase6_client
    created = client.post(f"/deliveries/orders/{ORDER}", json={"carrier_name": "Local courier"})
    assert created.status_code == 201
    delivery_id = created.json()["id"]
    assert client.patch(f"/deliveries/{delivery_id}/status", json={"status": "DELIVERED"}).status_code == 409
    assert client.patch(f"/deliveries/{delivery_id}/status", json={"status": "PICKED_UP"}).status_code == 200
    assert client.patch(f"/deliveries/{delivery_id}/status", json={"status": "IN_TRANSIT"}).json()["status"] == "IN_TRANSIT"
    assert orders.order["order_status"] == OrderStatus.IN_TRANSIT.value
    assert client.patch(f"/deliveries/{delivery_id}/status", json={"status": "DELIVERED"}).json()["status"] == "DELIVERED"
    current["user"] = public_user(BUYER, UserRole.BUYER)
    confirmed = client.post(f"/deliveries/{delivery_id}/confirm")
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "CONFIRMED"
    assert orders.order["order_status"] == OrderStatus.COMPLETED.value
    assert len(deliveries.get(delivery_id)["events"]) == 5


def test_delivery_access_and_invalid_confirm_are_rejected(phase6_client):
    client, current, _, _, _ = phase6_client
    created = client.post(f"/deliveries/orders/{ORDER}", json={})
    delivery_id = created.json()["id"]
    current["user"] = public_user(BUYER, UserRole.BUYER)
    assert client.patch(f"/deliveries/{delivery_id}/status", json={"status": "PICKED_UP"}).status_code == 403
    assert client.post(f"/deliveries/{delivery_id}/confirm").status_code == 409


def test_dispute_review_is_audited_and_blocks_until_resolution(phase6_client):
    client, current, orders, _, disputes = phase6_client
    current["user"] = public_user(BUYER, UserRole.BUYER)
    opened = client.post("/disputes", json={"order_id": ORDER, "reason": "DAMAGED_PRODUCE", "description": "Produce arrived damaged and cannot be sold."})
    assert opened.status_code == 201
    dispute_id = opened.json()["id"]
    assert orders.order["order_status"] == OrderStatus.DISPUTED.value
    assert client.patch(f"/disputes/{dispute_id}/review", json={"status": "UNDER_REVIEW", "resolution": "Reviewing delivery evidence and seller response."}).status_code == 403
    current["user"] = public_user(ADMIN, UserRole.ADMIN)
    reviewed = client.patch(f"/disputes/{dispute_id}/review", json={"status": "UNDER_REVIEW", "resolution": "Reviewing delivery evidence and seller response."})
    assert reviewed.status_code == 200
    resolved = client.patch(f"/disputes/{dispute_id}/review", json={"status": "RESOLVED", "decision": "REFUND_BUYER", "resolution": "Refund is approved; use the configured provider workflow."})
    assert resolved.status_code == 200
    assert resolved.json()["decisions"][-1]["admin_id"] == ADMIN
    assert orders.order["order_status"] == OrderStatus.READY_FOR_DELIVERY.value
    assert len(disputes.get(dispute_id)["decisions"]) == 2


def test_dispute_duplicate_and_invalid_admin_decision_conflict(phase6_client):
    client, current, _, _, _ = phase6_client
    current["user"] = public_user(BUYER, UserRole.BUYER)
    body = {"order_id": ORDER, "reason": "OTHER", "description": "Payment is confirmed but the delivery is delayed."}
    assert client.post("/disputes", json=body).status_code == 201
    assert client.post("/disputes", json=body).status_code == 409
    current["user"] = public_user(ADMIN, UserRole.ADMIN)
    dispute_id = next(iter(phase6_client[4].items))
    response = client.patch(f"/disputes/{dispute_id}/review", json={"status": "RESOLVED", "resolution": "A decision is required before resolution is final."})
    assert response.status_code == 409


def test_dispute_can_be_closed_after_resolution(phase6_client):
    client, current, _, _, disputes = phase6_client
    current["user"] = public_user(BUYER, UserRole.BUYER)
    opened = client.post("/disputes", json={"order_id": ORDER, "reason": "OTHER", "description": "Payment arrived but produce quality needs investigation."})
    dispute_id = opened.json()["id"]
    current["user"] = public_user(ADMIN, UserRole.ADMIN)
    assert client.patch(f"/disputes/{dispute_id}/review", json={"status":"RESOLVED","decision":"NO_FINANCIAL_ACTION","resolution":"Evidence reviewed; no financial action is required."}).status_code == 200
    closed = client.patch(f"/disputes/{dispute_id}/review", json={"status":"CLOSED","resolution":"Administrative case file is closed after resolution."})
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
    assert len(disputes.get(dispute_id)["decisions"]) == 2


def test_payout_route_returns_mock_simulation_and_is_idempotent(phase6_client, monkeypatch):
    client, current, orders, _, _ = phase6_client
    escrow_id = str(ObjectId())
    orders.order["order_status"] = OrderStatus.COMPLETED.value

    class MemoryEscrows:
        def __init__(self):
            self.item = {"id":escrow_id,"order_id":ORDER,"payment_id":str(ObjectId()),"provider":"mock","status":"PAYMENT_RECEIVED","custody_status":"NOT_SAFEGUARDED","actual_funds_safeguarded":False,"amount_kes":600,"commission_kes":30,"seller_amount_kes":570,"created_at":datetime.now(timezone.utc),"updated_at":datetime.now(timezone.utc)}

        def get(self, eid): return deepcopy(self.item) if eid == escrow_id else None
        def has_unresolved_dispute(self, order_id): return False
        def transition(self, eid, allowed, target, changes=None):
            if eid != escrow_id or self.item["status"] not in allowed: return None
            self.item.update(deepcopy(changes or {}),status=target,updated_at=datetime.now(timezone.utc))
            return deepcopy(self.item)

    class MemoryLedger:
        def __init__(self): self.items = {}
        def append(self, event): self.items.setdefault(event["event_key"],deepcopy(event)); return deepcopy(self.items[event["event_key"]])

    escrows, ledger = MemoryEscrows(), MemoryLedger()
    app.dependency_overrides[get_escrow_repository] = lambda: escrows
    app.dependency_overrides[get_ledger_repository] = lambda: ledger
    app.dependency_overrides[escrow_provider] = MockEscrowProvider
    monkeypatch.setattr(settings,"escrow_provider","mock")
    monkeypatch.setattr(settings,"app_env","test")
    current["user"] = public_user(SELLER, UserRole.FARMER)
    first = client.post(f"/payouts/{escrow_id}/release")
    assert first.status_code == 200
    assert first.json()["status"] == "SIMULATED_SETTLEMENT"
    again = client.post(f"/payouts/{escrow_id}/release")
    assert again.status_code == 200
    assert len([e for e in ledger.items.values() if e["event_type"] == "MOCK_SETTLEMENT_SIMULATED"]) == 1
