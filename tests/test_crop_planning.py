from datetime import date, datetime, timezone

from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.dependencies import get_advisory_repository, get_crop_repository, get_current_user, get_farm_repository
from app.main import app
from app.models.user import UserRole
from app.schemas.user import UserPublic

FARMER = "64b000000000000000000051"
OTHER = "64b000000000000000000052"
FARM = "64b000000000000000000053"
CROP = "64b000000000000000000054"


def user(uid=FARMER, role=UserRole.FARMER):
    now = datetime.now(timezone.utc)
    return UserPublic(id=uid, full_name="Test Farmer", email="farmer@example.test", phone="0712345678", role=role, is_active=True, created_at=now, updated_at=now)


class Farms:
    def get(self, farm_id):
        return {"id": FARM, "owner_id": FARMER, "county": "Nakuru", "name": "Test Farm"} if farm_id == FARM else None


class Crops:
    def __init__(self, name="Maize"):
        self.name = name

    def get(self, crop_id):
        if crop_id != CROP:
            return None
        return {"id": CROP, "owner_id": FARMER, "farm_id": FARM, "name": self.name, "planting_date": date(2026, 10, 1)}


class Advisories:
    def __init__(self):
        self.items = []

    def create(self, values):
        item = {**values, "id": str(ObjectId()), "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
        self.items.append(item)
        return item


def setup_client(monkeypatch, crop_name="Maize"):
    current = {"user": user()}
    advisories = Advisories()
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    app.dependency_overrides[get_farm_repository] = Farms
    app.dependency_overrides[get_crop_repository] = lambda: Crops(crop_name)
    app.dependency_overrides[get_advisory_repository] = lambda: advisories
    client = TestClient(app)
    return client, current, advisories


def test_stage_calendar_is_source_linked_and_does_not_invent_dates_or_rates(monkeypatch):
    client, _, _ = setup_client(monkeypatch, crop_name="Tomatoes")
    try:
        response = client.get(f"/crop-planning/crops/{CROP}/calendar")
        assert response.status_code == 200
        body = response.json()
        assert body["crop_name"] == "Tomato"
        assert body["schedule_type"] == "STAGE_ORDER_ONLY"
        assert body["planting_date"] == "2026-10-01"
        assert body["sources"][0]["organization"] == "KALRO"
        assert all(stage["actions"] for stage in body["stages"])
        assert "does not infer county planting dates" in body["message"]
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_crop_calendar_hides_foreign_and_unsupported_crops(monkeypatch):
    client, current, _ = setup_client(monkeypatch, crop_name="Rice")
    try:
        unsupported = client.get(f"/crop-planning/crops/{CROP}/calendar")
        assert unsupported.status_code == 404
        current["user"] = user(OTHER)
        foreign = client.get(f"/crop-planning/crops/{CROP}/calendar")
        assert foreign.status_code == 404
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_soil_guidance_is_saved_and_never_generates_fertilizer_rates(monkeypatch):
    client, _, repository = setup_client(monkeypatch)
    try:
        response = client.post("/crop-planning/soil-guidance", json={"farm_id": FARM, "crop_id": CROP})
        assert response.status_code == 201
        body = response.json()
        assert body["kind"] == "SOIL_EDUCATION"
        assert body["soil_test_recommended"] is True
        assert body["precise_rates_provided"] is False
        assert "does not interpret nutrient values" in body["message"] or "soil test" in body["message"].lower()
        assert all(source["organization"].startswith("Ministry of Agriculture") for source in body["sources"])
        assert len(repository.items) == 1
        assert "NO_UNSUPPORTED_NUTRIENT_RATES" in body["rules_applied"]
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_soil_guidance_rejects_mismatched_or_foreign_farm_crop(monkeypatch):
    client, current, _ = setup_client(monkeypatch)
    try:
        assert client.post("/crop-planning/soil-guidance", json={"farm_id": "64b000000000000000000099", "crop_id": CROP}).status_code == 404
        current["user"] = user(OTHER)
        assert client.post("/crop-planning/soil-guidance", json={"farm_id": FARM, "crop_id": CROP}).status_code == 404
    finally:
        client.close()
        app.dependency_overrides.clear()
