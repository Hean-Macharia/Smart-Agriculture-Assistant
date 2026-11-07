from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_user, get_marketplace_repository, get_order_repository
from app.main import app
from app.models.marketplace import ProductAvailability
from app.models.order import OrderStatus, PaymentStatus
from app.models.user import UserRole
from app.schemas.order import DeliveryInformation, OrderCreate
from app.schemas.user import UserPublic
from app.services.order_service import StockUnavailableError, place_order

FARMER_ID = "64b000000000000000000001"
OTHER_FARMER_ID = "64b000000000000000000002"
BUYER_ID = "64b000000000000000000003"
OTHER_BUYER_ID = "64b000000000000000000004"


class MemoryMarketplace:
    def __init__(self):
        self.items = {}
        self.lock = Lock()

    def create(self, farmer_id, values):
        now = datetime.now(timezone.utc)
        doc = {**deepcopy(values), "id": str(ObjectId()), "farmer_id": farmer_id, "availability_status": "ACTIVE", "created_at": now, "updated_at": now, "_reservations": set(), "is_active": True}
        self.items[doc["id"]] = doc
        return self._copy(doc)

    @staticmethod
    def _copy(doc):
        return {k: deepcopy(v) for k, v in doc.items() if not k.startswith("_") and k != "is_active"}

    def get(self, product_id, active_only=True):
        doc = self.items.get(product_id)
        if doc and (not active_only or doc["is_active"]):
            return self._copy(doc)
        return None

    def list_products(self, *, search, county, category, min_price, max_price, skip, limit):
        docs = [d for d in self.items.values() if d["is_active"] and d["availability_status"] == "ACTIVE" and d["quantity_available"] > 0]
        if search:
            docs = [d for d in docs if search.lower() in d["product_name"].lower()]
        if county:
            docs = [d for d in docs if county.lower() == d["county"].lower()]
        if category:
            docs = [d for d in docs if category.lower() == d["category"].lower()]
        if min_price is not None:
            docs = [d for d in docs if d["price_per_unit_kes"] >= min_price]
        if max_price is not None:
            docs = [d for d in docs if d["price_per_unit_kes"] <= max_price]
        return [self._copy(d) for d in docs[skip:skip + limit]], len(docs)

    def list_for_farmer(self, farmer_id, *, skip, limit):
        docs = [d for d in self.items.values() if d["farmer_id"] == farmer_id and d["is_active"]]
        return [self._copy(d) for d in docs[skip:skip + limit]], len(docs)

    def update(self, product_id, farmer_id, changes):
        with self.lock:
            doc = self.items.get(product_id)
            if not doc or doc["farmer_id"] != farmer_id or not doc["is_active"]:
                return None
            doc.update(deepcopy(changes))
            if "quantity_available" in changes:
                doc["availability_status"] = "ACTIVE" if changes["quantity_available"] else "SOLD_OUT"
            doc["updated_at"] = datetime.now(timezone.utc)
            return self._copy(doc)

    def deactivate(self, product_id, farmer_id):
        doc = self.items.get(product_id)
        if not doc or doc["farmer_id"] != farmer_id or not doc["is_active"]:
            return False
        doc["is_active"] = False
        doc["availability_status"] = "INACTIVE"
        return True

    def reserve_stock(self, product_id, quantity, order_id):
        with self.lock:
            doc = self.items.get(product_id)
            if not doc or not doc["is_active"] or doc["availability_status"] != "ACTIVE" or doc["quantity_available"] < quantity:
                return None
            doc["quantity_available"] -= quantity
            doc["_reservations"].add(order_id)
            if doc["quantity_available"] == 0:
                doc["availability_status"] = "SOLD_OUT"
            return self._copy(doc)

    def release_stock(self, product_id, quantity, order_id):
        with self.lock:
            doc = self.items.get(product_id)
            if not doc or order_id not in doc["_reservations"]:
                return False
            doc["_reservations"].remove(order_id)
            doc["quantity_available"] += quantity
            if doc["is_active"]:
                doc["availability_status"] = "ACTIVE"
            return True


class MemoryOrders:
    def __init__(self):
        self.items = {}
        self.lock = Lock()

    @staticmethod
    def _copy(doc):
        result = deepcopy(doc)
        result["id"] = str(result.pop("_id"))
        for key in ("buyer_id", "seller_id", "product_id"):
            result[key] = str(result[key])
        return result

    def create(self, values):
        with self.lock:
            doc = {**deepcopy(values), "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
            doc["_id"] = doc.get("_id", ObjectId())
            self.items[str(doc["_id"])] = doc
            return self._copy(doc)

    def get(self, order_id):
        doc = self.items.get(order_id)
        return self._copy(doc) if doc else None

    def list_for_user(self, field, user_id, *, skip, limit):
        docs = [d for d in self.items.values() if str(d[field]) == user_id]
        return [self._copy(d) for d in docs[skip:skip + limit]], len(docs)

    def transition(self, order_id, allowed_current, target):
        with self.lock:
            doc = self.items.get(order_id)
            if not doc or doc["order_status"] not in allowed_current:
                return None
            doc["order_status"] = target
            doc["updated_at"] = datetime.now(timezone.utc)
            return self._copy(doc)


@pytest.fixture
def phase4_client():
    products, orders = MemoryMarketplace(), MemoryOrders()
    active = {"user": UserPublic(id=FARMER_ID, full_name="Farmer One", email="farmer@example.test", phone="+254712345678", role=UserRole.FARMER, is_active=True, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))}
    app.dependency_overrides[get_marketplace_repository] = lambda: products
    app.dependency_overrides[get_order_repository] = lambda: orders
    app.dependency_overrides[get_current_user] = lambda: active["user"]
    with TestClient(app) as client:
        yield client, active, products, orders
    app.dependency_overrides.clear()


def product_payload(quantity=10):
    return {"product_name": "White Maize", "category": "Grains", "description": "Dry, cleaned maize grains.", "quantity_available": quantity, "unit": "kg", "price_per_unit_kes": 60, "county": "Kiambu", "sub_county": "Limuru", "product_images": []}


def delivery():
    return {"recipient_name": "Buyer One", "recipient_phone": "0712345678", "county": "Nairobi", "sub_county": "Westlands", "location": "Westlands", "instructions": "Call on arrival"}


def test_product_create_browse_filters_owner_update_and_deactivate(phase4_client):
    client, active, products, _ = phase4_client
    created = client.post("/marketplace/products", json=product_payload())
    assert created.status_code == 201
    product_id = created.json()["id"]
    assert created.json()["farmer_id"] == FARMER_ID
    assert client.get("/marketplace/products?search=maize&county=Kiambu&category=grains&min_price_kes=50&max_price_kes=70").json()["total"] == 1
    assert client.patch(f"/marketplace/products/{product_id}", json={"price_per_unit_kes": 65}).json()["price_per_unit_kes"] == 65
    active["user"] = active["user"].model_copy(update={"id": OTHER_FARMER_ID})
    assert client.patch(f"/marketplace/products/{product_id}", json={"price_per_unit_kes": 1}).status_code == 404
    active["user"] = active["user"].model_copy(update={"id": FARMER_ID})
    assert client.delete(f"/marketplace/products/{product_id}").status_code == 204
    assert client.get("/marketplace/products").json()["total"] == 0
    assert products.get(product_id) is None


def test_buyer_order_reserves_stock_and_cancel_restores_once(phase4_client):
    client, active, _, _ = phase4_client
    product_id = client.post("/marketplace/products", json=product_payload(5)).json()["id"]
    active["user"] = active["user"].model_copy(update={"id": BUYER_ID, "role": UserRole.BUYER})
    response = client.post("/orders", json={"product_id": product_id, "quantity": 3, "delivery_information": delivery()})
    assert response.status_code == 201
    order_id = response.json()["id"]
    assert response.json()["total_amount_kes"] == 180
    assert response.json()["order_status"] == "AWAITING_PAYMENT"
    assert response.json()["payment_status"] == "UNPAID"
    assert client.get("/marketplace/products").json()["items"][0]["quantity_available"] == 2
    assert client.post(f"/orders/{order_id}/cancel").json()["order_status"] == "CANCELLED"
    assert client.post(f"/orders/{order_id}/cancel").status_code == 200
    assert client.get(f"/marketplace/products/{product_id}").json()["quantity_available"] == 5


def test_orders_enforce_stock_self_purchase_and_private_ownership(phase4_client):
    client, active, _, _ = phase4_client
    product_id = client.post("/marketplace/products", json=product_payload(2)).json()["id"]
    active["user"] = active["user"].model_copy(update={"id": BUYER_ID, "role": UserRole.BUYER})
    too_much = client.post("/orders", json={"product_id": product_id, "quantity": 3, "delivery_information": delivery()})
    assert too_much.status_code == 409
    order = client.post("/orders", json={"product_id": product_id, "quantity": 2, "delivery_information": delivery()}).json()
    assert order["order_status"] == "AWAITING_PAYMENT"
    assert client.get(f"/orders/{order['id']}").status_code == 200
    active["user"] = active["user"].model_copy(update={"id": OTHER_BUYER_ID})
    assert client.get(f"/orders/{order['id']}").status_code == 404
    active["user"] = active["user"].model_copy(update={"id": BUYER_ID})
    assert client.post("/orders", json={"product_id": product_id, "quantity": 1, "delivery_information": delivery()}).status_code == 409


def test_concurrent_order_requests_cannot_oversell():
    products, orders = MemoryMarketplace(), MemoryOrders()
    product = products.create(FARMER_ID, product_payload(5))
    payload = OrderCreate(product_id=product["id"], quantity=2, delivery_information=DeliveryInformation(**delivery()))

    def attempt(_):
        try:
            place_order(orders, products, BUYER_ID, payload)
            return True
        except StockUnavailableError:
            return False

    with ThreadPoolExecutor(max_workers=12) as pool:
        successful = list(pool.map(attempt, range(12)))
    assert sum(successful) == 2
    assert products.get(product["id"])["quantity_available"] == 1
    assert len(orders.items) == 2


def test_paid_order_status_cannot_be_faked_by_seller_endpoint(phase4_client):
    client, active, _, orders = phase4_client
    product_id = client.post("/marketplace/products", json=product_payload()).json()["id"]
    active["user"] = active["user"].model_copy(update={"id": BUYER_ID, "role": UserRole.BUYER})
    created = client.post("/orders", json={"product_id": product_id, "quantity": 1, "delivery_information": delivery()}).json()
    active["user"] = active["user"].model_copy(update={"id": FARMER_ID, "role": UserRole.FARMER})
    assert client.patch(f"/orders/{created['id']}/status", json={"order_status": "PAID"}).status_code == 409
    assert client.patch(f"/orders/{created['id']}/status", json={"order_status": "PROCESSING"}).status_code == 409
    doc = orders.items[created["id"]]
    doc["order_status"] = OrderStatus.PAID.value
    doc["payment_status"] = PaymentStatus.PAID.value
    assert client.patch(f"/orders/{created['id']}/status", json={"order_status": "PROCESSING"}).status_code == 200
    assert client.patch(f"/orders/{created['id']}/status", json={"order_status": "READY_FOR_DELIVERY"}).status_code == 200
