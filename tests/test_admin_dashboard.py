from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.dependencies import get_admin_repository, get_user_repository
from app.main import app
from app.repositories.user_repository import UserConflictError


class MemoryUsers:
    def __init__(self):
        self.items = {}

    def create_user(self, values, *, bootstrap_admin=False):
        if any(item["email"] == values["email"] for item in self.items.values()):
            raise UserConflictError
        item = {**values, "_id": ObjectId(), "is_active": True, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc), "bootstrap_admin": bootstrap_admin}
        self.items[str(item["_id"])] = item
        return deepcopy(item)

    def get_by_email(self, email):
        return deepcopy(next((item for item in self.items.values() if item["email"] == email), None))

    def get_by_id(self, user_id):
        return deepcopy(self.items.get(user_id))

    def count_admins(self):
        return sum(item["role"] == "ADMIN" for item in self.items.values())


class MemoryAdmin:
    def overview(self):
        return {"counts": {"users": {"farmer": 1, "buyer": 0, "agricultural_officer": 0, "admin": 1}}, "trends": {"users": [], "products": [], "orders": [], "payments": []}, "disease_by_condition": [], "disease_by_crop": [], "marketplace_by_county": []}

    def list_people(self, *, role, search, skip, limit):
        del search, skip
        return ([{"id": "safe-user", "full_name": "Amina Farmer", "role": role, "farm_count": 2}], 1) if limit else ([], 0)

    def list_audit(self, *, actor_id, action, skip, limit):
        del actor_id, action, skip, limit
        return [], 0


@pytest.fixture
def admin_client(monkeypatch):
    from app.core import config

    users = MemoryUsers()
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides[get_admin_repository] = MemoryAdmin
    monkeypatch.setattr(config.settings, "jwt_secret_key", "admin-dashboard-test-signing-key-123456")
    monkeypatch.setattr(config.settings, "admin_bootstrap_token", "admin-dashboard-test-bootstrap-token-123456")
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_admin_dashboard_endpoints_require_admin_and_return_database_shaped_views(admin_client):
    client = admin_client
    assert client.get("/admin/overview").status_code == 401

    farmer = {"full_name": "Amina Farmer", "email": "farmer@example.test", "phone": "0712345678", "password": "FarmerStrong!234"}
    assert client.post("/auth/register/farmer", json=farmer).status_code == 201
    farmer_login = client.post("/auth/login", json={"email": farmer["email"], "password": farmer["password"]}).json()
    farmer_headers = {"Authorization": f"Bearer {farmer_login['access_token']}"}
    assert client.get("/admin/overview", headers=farmer_headers).status_code == 403

    created = client.post(
        "/auth/bootstrap-admin",
        headers={"X-Admin-Bootstrap-Token": "admin-dashboard-test-bootstrap-token-123456"},
        json={"full_name": "Project Admin", "email": "admin@example.test", "phone": "0712345679", "password": "AdminStrong!234"},
    )
    assert created.status_code == 201
    login = client.post("/auth/login", json={"email": "admin@example.test", "password": "AdminStrong!234"}).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    overview = client.get("/admin/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["counts"]["users"]["farmer"] == 1

    people = client.get("/admin/people?role=FARMER", headers=headers)
    assert people.status_code == 200
    assert people.json()["items"][0]["farm_count"] == 2
    assert "password_hash" not in people.text

    assert client.get("/admin/audit-logs", headers=headers).status_code == 200
