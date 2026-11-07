from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import get_user_repository
from app.core.security import verify_password
from app.main import app
from app.repositories.user_repository import UserConflictError

TEST_JWT_SECRET = "phase-two-test-key-0123456789-0123456789"
TEST_BOOTSTRAP_TOKEN = "phase-two-admin-bootstrap-token-0123456789"


class InMemoryUserRepository:
    """Isolated auth test double; these tests never connect to MongoDB."""

    def __init__(self):
        self.documents: dict[str, dict] = {}

    def create_user(self, values: dict, *, bootstrap_admin: bool = False) -> dict:
        if any(
            doc["email"] == values["email"] or doc["phone"] == values["phone"]
            for doc in self.documents.values()
        ):
            raise UserConflictError
        if bootstrap_admin and any(doc.get("bootstrap_admin") for doc in self.documents.values()):
            raise UserConflictError
        now = datetime.now(timezone.utc)
        document = {
            **deepcopy(values),
            "_id": str(uuid4()),
            "is_active": True,
            "bootstrap_admin": bootstrap_admin,
            "created_at": now,
            "updated_at": now,
        }
        self.documents[document["_id"]] = document
        return deepcopy(document)

    def get_by_email(self, email: str):
        return next((deepcopy(doc) for doc in self.documents.values() if doc["email"] == email), None)

    def get_by_id(self, user_id: str):
        doc = self.documents.get(user_id)
        return deepcopy(doc) if doc else None

    def count_admins(self) -> int:
        return sum(doc["role"] == "ADMIN" for doc in self.documents.values())

    def list_users(self, *, skip: int, limit: int, role: str | None = None):
        docs = [doc for doc in self.documents.values() if role is None or doc["role"] == role]
        return [deepcopy(doc) for doc in docs[skip : skip + limit]], len(docs)

    def update_profile(self, user_id: str, changes: dict):
        doc = self.documents.get(user_id)
        if doc is None:
            return None
        if "phone" in changes and any(
            other_id != user_id and other["phone"] == changes["phone"]
            for other_id, other in self.documents.items()
        ):
            raise UserConflictError
        doc.update(changes)
        doc["updated_at"] = datetime.now(timezone.utc)
        return deepcopy(doc)


@pytest.fixture

def client(monkeypatch):
    from app.core import config

    users = InMemoryUserRepository()
    monkeypatch.setattr(config.settings, "jwt_secret_key", TEST_JWT_SECRET)
    monkeypatch.setattr(config.settings, "admin_bootstrap_token", TEST_BOOTSTRAP_TOKEN)
    app.dependency_overrides[get_user_repository] = lambda: users
    with TestClient(app) as test_client:
        yield test_client, users
    app.dependency_overrides.clear()


def farmer_payload(email="farmer@example.test", phone="0712345678", password="FarmPass!234"):
    return {
        "full_name": "Amina Farmer",
        "email": email,
        "phone": phone,
        "password": password,
    }


def test_farmer_registration_login_current_user_and_profile_update(client):
    api, users = client
    payload = farmer_payload()

    registered = api.post("/auth/register/farmer", json=payload)
    assert registered.status_code == 201
    body = registered.json()
    assert body["role"] == "FARMER"
    assert body["phone"] == "+254712345678"
    assert "password" not in body and "password_hash" not in body
    saved = users.get_by_email("farmer@example.test")
    assert saved["password_hash"] != payload["password"]
    assert verify_password(payload["password"], saved["password_hash"])

    login = api.post(
        "/auth/login",
        json={"email": "FARMER@EXAMPLE.TEST", "password": payload["password"]},
    )
    assert login.status_code == 200
    token_body = login.json()
    assert token_body["token_type"] == "bearer"
    assert token_body["expires_in"] > 0
    assert token_body["user"]["id"] == body["id"]

    headers = {"Authorization": f"Bearer {token_body['access_token']}"}
    current = api.get("/auth/me", headers=headers)
    assert current.status_code == 200
    assert current.json()["role"] == "FARMER"

    updated = api.patch("/auth/me", headers=headers, json={"full_name": "Amina Wanjiku"})
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Amina Wanjiku"


def test_buyer_registration_and_role_protection(client):
    api, _ = client
    buyer = {
        "full_name": "Buyer One",
        "email": "buyer@example.test",
        "phone": "0723456789",
        "password": "BuyerPass!234",
    }
    assert api.post("/auth/register/buyer", json=buyer).status_code == 201
    login = api.post("/auth/login", json={"email": buyer["email"], "password": buyer["password"]})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert api.get("/auth/admin/users", headers=headers).status_code == 403
    assert api.post("/auth/admin/users", headers=headers, json={}).status_code == 403


def test_invalid_credentials_missing_auth_and_bad_token(client):
    api, _ = client
    assert api.post("/auth/login", json={"email": "unknown@example.test", "password": "WrongPass!234"}).status_code == 401
    assert api.get("/auth/me").status_code == 401
    assert api.get("/auth/me", headers={"Authorization": "Bearer invalid.token.value"}).status_code == 401


def test_duplicate_registration_and_invalid_input(client):
    api, _ = client
    payload = farmer_payload()
    assert api.post("/auth/register/farmer", json=payload).status_code == 201
    duplicate = {**payload, "phone": "0711111111"}
    assert api.post("/auth/register/farmer", json=duplicate).status_code == 409
    invalid = {**payload, "email": "not-an-email", "phone": "123", "password": "short"}
    assert api.post("/auth/register/farmer", json=invalid).status_code == 422


def test_bootstrap_admin_once_then_admin_manages_officer_accounts(client):
    api, _ = client
    bootstrap = farmer_payload("admin@example.test", "0712345679", "AdminPass!234")
    headers = {"X-Admin-Bootstrap-Token": TEST_BOOTSTRAP_TOKEN}

    created = api.post("/auth/bootstrap-admin", json=bootstrap, headers=headers)
    assert created.status_code == 201
    assert created.json()["role"] == "ADMIN"
    assert api.post("/auth/bootstrap-admin", json=bootstrap, headers=headers).status_code == 409

    login = api.post("/auth/login", json={"email": bootstrap["email"], "password": bootstrap["password"]})
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    officer = {
        "full_name": "Officer One",
        "email": "officer@example.test",
        "phone": "0712345680",
        "password": "OfficerPass!234",
        "role": "AGRICULTURAL_OFFICER",
    }
    response = api.post("/auth/admin/users", json=officer, headers=admin_headers)
    assert response.status_code == 201
    assert response.json()["role"] == "AGRICULTURAL_OFFICER"

    listed = api.get("/auth/admin/users?limit=10", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert all("password_hash" not in user for user in listed.json()["items"])


def test_admin_bootstrap_rejects_bad_token_and_public_role_injection(client):
    api, _ = client
    payload = farmer_payload("bad-admin@example.test", "0712345681", "AdminPass!234")
    assert api.post("/auth/bootstrap-admin", json=payload, headers={"X-Admin-Bootstrap-Token": "wrong"}).status_code == 403

    buyer = {**payload, "role": "ADMIN"}
    assert api.post("/auth/register/buyer", json=buyer).status_code == 422
