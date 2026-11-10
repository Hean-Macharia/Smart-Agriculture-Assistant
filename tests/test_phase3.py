from copy import deepcopy
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.dependencies import (
    get_buyer_repository,
    get_crop_repository,
    get_current_user,
    get_farm_repository,
    get_farmer_repository,
)
from app.main import app
from app.models.user import UserRole
from app.schemas.user import UserPublic

FARMER_ID = "64b000000000000000000001"
OTHER_FARMER_ID = "64b000000000000000000002"
BUYER_ID = "64b000000000000000000003"


class MemoryProfiles:
    def __init__(self):
        self.data = {}

    def upsert_profile(self, user_id, values):
        now = datetime.now(timezone.utc)
        doc = self.data.get(user_id, {
            "id": str(ObjectId()), "user_id": user_id, "created_at": now,
        })
        doc.update(deepcopy(values), updated_at=now)
        self.data[user_id] = doc
        return deepcopy(doc)

    def get_profile(self, user_id):
        return deepcopy(self.data.get(user_id))


class MemoryFarms:
    def __init__(self):
        self.data = {}

    def create(self, owner_id, values):
        now = datetime.now(timezone.utc)
        doc = {**deepcopy(values), "id": str(ObjectId()), "owner_id": owner_id, "is_active": True, "created_at": now, "updated_at": now}
        self.data[doc["id"]] = doc
        return deepcopy(doc)

    def get(self, farm_id, active_only=True):
        doc = self.data.get(farm_id)
        if doc and (not active_only or doc["is_active"]):
            return deepcopy(doc)
        return None

    def list_for_owner(self, owner_id, *, skip, limit):
        docs = [deepcopy(d) for d in self.data.values() if d["owner_id"] == owner_id and d["is_active"]]
        return docs[skip:skip + limit], len(docs)

    def update(self, farm_id, owner_id, changes):
        doc = self.data.get(farm_id)
        if not doc or doc["owner_id"] != owner_id or not doc["is_active"]:
            return None
        doc.update(deepcopy(changes), updated_at=datetime.now(timezone.utc))
        return deepcopy(doc)

    def deactivate(self, farm_id, owner_id):
        doc = self.data.get(farm_id)
        if not doc or doc["owner_id"] != owner_id or not doc["is_active"]:
            return False
        doc["is_active"] = False
        return True


class MemoryCrops:
    def __init__(self):
        self.data = {}

    def create(self, owner_id, values):
        now = datetime.now(timezone.utc)
        doc = {**deepcopy(values), "id": str(ObjectId()), "owner_id": owner_id, "is_active": True, "created_at": now, "updated_at": now}
        self.data[doc["id"]] = doc
        return deepcopy(doc)

    def get(self, crop_id, active_only=True):
        doc = self.data.get(crop_id)
        if doc and (not active_only or doc["is_active"]):
            return deepcopy(doc)
        return None

    def list_for_owner(self, owner_id, *, farm_id, skip, limit):
        docs = [deepcopy(d) for d in self.data.values() if d["owner_id"] == owner_id and d["is_active"] and (not farm_id or d["farm_id"] == farm_id)]
        return docs[skip:skip + limit], len(docs)

    def update(self, crop_id, owner_id, changes):
        doc = self.data.get(crop_id)
        if not doc or doc["owner_id"] != owner_id or not doc["is_active"]:
            return None
        doc.update(deepcopy(changes), updated_at=datetime.now(timezone.utc))
        return deepcopy(doc)

    def deactivate(self, crop_id, owner_id):
        doc = self.data.get(crop_id)
        if not doc or doc["owner_id"] != owner_id or not doc["is_active"]:
            return False
        doc["is_active"] = False
        return True


@pytest.fixture
def phase3_client():
    profiles, buyer_profiles, farms, crops = MemoryProfiles(), MemoryProfiles(), MemoryFarms(), MemoryCrops()
    active = {"user": UserPublic(id=FARMER_ID, full_name="A Farmer", email="a@example.test", phone="+254712345678", role=UserRole.FARMER, is_active=True, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))}

    app.dependency_overrides[get_farmer_repository] = lambda: profiles
    app.dependency_overrides[get_buyer_repository] = lambda: buyer_profiles
    app.dependency_overrides[get_farm_repository] = lambda: farms
    app.dependency_overrides[get_crop_repository] = lambda: crops
    app.dependency_overrides[get_current_user] = lambda: active["user"]
    with TestClient(app) as client:
        yield client, active, farms, crops
    app.dependency_overrides.clear()


def farm_payload(name="Green Valley"):
    return {"name": name, "county": "Kiambu", "sub_county": "Limuru", "location": "Ndeiya", "size_acres": 2.5, "soil_type": "Clay loam", "irrigation_available": True}


def test_farmer_profile_upsert_and_role_protection(phase3_client):
    client, active, _, _ = phase3_client
    data = {"county": "Kiambu", "sub_county": "Limuru", "location": "Ndeiya", "farm_size_acres": 2.5, "soil_type": "Clay loam", "irrigation_available": True, "crops_grown": ["maize", "beans"]}
    farmer_response = client.put("/farmers/me", json=data)
    assert farmer_response.status_code == 200
    assert "created_at" in farmer_response.json() and "updated_at" in farmer_response.json()
    got = client.get("/farmers/me")
    assert got.status_code == 200 and got.json()["crops_grown"] == ["maize", "beans"]
    assert "created_at" in got.json() and "updated_at" in got.json()
    active["user"] = active["user"].model_copy(update={"role": UserRole.BUYER, "id": BUYER_ID})
    assert client.get("/farmers/me").status_code == 403
    buyer_data = {"county": "Nairobi", "sub_county": "Westlands", "delivery_location": "Westlands", "organization_name": "Market"}
    buyer_response = client.put("/buyers/me", json=buyer_data)
    assert buyer_response.status_code == 200
    assert "created_at" in buyer_response.json() and "updated_at" in buyer_response.json()
    buyer_get = client.get("/buyers/me")
    assert buyer_get.json()["organization_name"] == "Market"
    assert "created_at" in buyer_get.json() and "updated_at" in buyer_get.json()
    assert client.post("/farms", json=farm_payload()).status_code == 403


def test_farm_crop_lifecycle_and_owner_isolation(phase3_client):
    client, active, _, _ = phase3_client
    created_farm = client.post("/farms", json=farm_payload())
    assert created_farm.status_code == 201
    farm_id = created_farm.json()["id"]
    assert client.get("/farms").json()["total"] == 1
    assert client.patch(f"/farms/{farm_id}", json={"size_acres": 3}).json()["size_acres"] == 3

    crop = {"farm_id": farm_id, "name": "Maize", "variety": "DK8031", "planting_date": "2026-03-01", "expected_harvest_date": "2026-07-01", "quantity": 250, "quantity_unit": "kg", "growth_information": "Vegetative stage"}
    response = client.post("/crops", json=crop)
    assert response.status_code == 201
    crop_id = response.json()["id"]
    assert response.json()["planting_date"] == "2026-03-01"
    assert client.get(f"/crops?farm_id={farm_id}").json()["total"] == 1
    assert client.patch(f"/crops/{crop_id}", json={"quantity": 300}).json()["quantity"] == 300
    assert client.patch(f"/crops/{crop_id}", json={"planting_date": "2026-08-01"}).status_code == 422

    active["user"] = active["user"].model_copy(update={"id": OTHER_FARMER_ID})
    assert client.get(f"/farms/{farm_id}").status_code == 404
    assert client.patch(f"/crops/{crop_id}", json={"quantity": 1}).status_code == 404
    assert client.delete(f"/farms/{farm_id}").status_code == 404


def test_crop_rejects_invalid_dates_and_non_owned_farm(phase3_client):
    client, _, farms, _ = phase3_client
    farm = farms.create(OTHER_FARMER_ID, farm_payload())
    data = {"farm_id": farm["id"], "name": "Beans", "planting_date": "2026-07-01", "expected_harvest_date": "2026-06-01"}
    assert client.post("/crops", json=data).status_code == 422
    data["expected_harvest_date"] = "2026-08-01"
    assert client.post("/crops", json=data).status_code == 404
    data["farm_id"] = "z" * 24
    assert client.post("/crops", json=data).status_code == 422
    assert client.post("/farms", json={**farm_payload(), "size_acres": -1}).status_code == 422


def test_soft_delete_removes_farm_and_crop_from_active_lists(phase3_client):
    client, _, _, _ = phase3_client
    farm_id = client.post("/farms", json=farm_payload()).json()["id"]
    crop = {"farm_id": farm_id, "name": "Tomato", "planting_date": "2026-02-01"}
    crop_id = client.post("/crops", json=crop).json()["id"]
    assert client.delete(f"/crops/{crop_id}").status_code == 204
    assert client.get("/crops").json()["total"] == 0
    assert client.delete(f"/farms/{farm_id}").status_code == 204
    assert client.get("/farms").json()["total"] == 0
