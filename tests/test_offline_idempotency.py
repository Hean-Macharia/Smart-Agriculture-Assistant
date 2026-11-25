from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.repositories.crop_repository import CropRepository
from app.repositories.farm_repository import FarmRepository


class MemoryCollection:
    def __init__(self):
        self.documents = []
        self.indexes = []

    def create_index(self, keys, **options):
        self.indexes.append((keys, options))

    def find_one(self, query):
        return next((doc.copy() for doc in self.documents if all(doc.get(key) == value for key, value in query.items())), None)

    def insert_one(self, document):
        if document.get("_client_operation_id"):
            same_operation = any(
                existing.get("owner_id") == document["owner_id"]
                and existing.get("_client_operation_id") == document["_client_operation_id"]
                for existing in self.documents
            )
            if same_operation:
                from pymongo.errors import DuplicateKeyError
                raise DuplicateKeyError("duplicate client operation")
        saved = document.copy()
        saved["_id"] = ObjectId()
        self.documents.append(saved)
        return type("InsertResult", (), {"inserted_id": saved["_id"]})()

    def update_one(self, query, update):
        for document in self.documents:
            if all(document.get(key) == value for key, value in query.items()):
                document.update(update["$set"])
                return type("UpdateResult", (), {"modified_count": 1})()
        return type("UpdateResult", (), {"modified_count": 0})()


def test_farm_create_is_idempotent_and_hides_internal_key():
    collection = MemoryCollection()
    repository = FarmRepository(collection)
    owner_id = str(ObjectId())
    values = {
        "name": "Njoro Shamba", "county": "Nakuru", "sub_county": "Njoro",
        "location": "Mau Narok", "size_acres": 3.5, "soil_type": "Loam",
        "irrigation_available": False, "latitude": None, "longitude": None,
    }

    first = repository.create(owner_id, values, idempotency_key="offline-farm-operation-001")
    retry = repository.create(owner_id, values, idempotency_key="offline-farm-operation-001")

    assert len(collection.documents) == 1
    assert retry["id"] == first["id"]
    assert first["updated_at"].microsecond % 1000 == 0
    assert "_client_operation_id" not in retry
    assert any(options.get("unique") and options.get("partialFilterExpression") for _, options in collection.indexes)


def test_reusing_farm_idempotency_key_with_different_body_conflicts():
    repository = FarmRepository(MemoryCollection())
    owner_id = str(ObjectId())
    values = {
        "name": "Farm One", "county": "Nakuru", "sub_county": "Njoro",
        "location": "Mau Narok", "size_acres": 3.5, "soil_type": "Loam",
        "irrigation_available": False, "latitude": None, "longitude": None,
    }
    repository.create(owner_id, values, idempotency_key="offline-farm-operation-002")

    with pytest.raises(ValueError, match="different request"):
        repository.create(owner_id, {**values, "name": "Changed Farm"}, idempotency_key="offline-farm-operation-002")


def test_crop_create_is_idempotent_and_returns_string_farm_id():
    collection = MemoryCollection()
    repository = CropRepository(collection)
    owner_id = str(ObjectId())
    farm_id = str(ObjectId())
    values = {
        "farm_id": farm_id, "name": "Tomatoes", "variety": None,
        "planting_date": "2026-11-01", "expected_harvest_date": None,
        "quantity": 10, "quantity_unit": "kg", "growth_information": "flowering",
    }

    first = repository.create(owner_id, values, idempotency_key="offline-crop-operation-001")
    retry = repository.create(owner_id, values, idempotency_key="offline-crop-operation-001")

    assert len(collection.documents) == 1
    assert retry["id"] == first["id"]
    assert retry["farm_id"] == farm_id
    assert "_client_operation_hash" not in retry


def test_conditional_crop_update_rejects_stale_timestamp():
    collection = MemoryCollection()
    repository = CropRepository(collection)
    owner_id = str(ObjectId())
    farm_id = ObjectId()
    created = repository.create(owner_id, {
        "farm_id": str(farm_id), "name": "Beans", "variety": None,
        "planting_date": "2026-11-01", "expected_harvest_date": None,
        "quantity": None, "quantity_unit": "kg", "growth_information": None,
    })
    stored = collection.documents[0]
    current = stored["updated_at"]
    assert current.microsecond % 1000 == 0
    stale = datetime(2020, 1, 1, tzinfo=timezone.utc)

    assert repository.update(created["id"], owner_id, {"growth_information": "stale note"}, expected_updated_at=stale) is None
    updated = repository.update(created["id"], owner_id, {"growth_information": "fresh note"}, expected_updated_at=current)
    assert updated["growth_information"] == "fresh note"


def test_conditional_farm_update_returns_updated_document_and_rejects_stale_timestamp():
    collection = MemoryCollection()
    repository = FarmRepository(collection)
    owner_id = str(ObjectId())
    created = repository.create(owner_id, {
        "name": "Njoro Farm", "county": "Nakuru", "sub_county": "Njoro",
        "location": "Mau Narok", "size_acres": 2, "soil_type": "Loam",
        "irrigation_available": False, "latitude": None, "longitude": None,
    })
    current = collection.documents[0]["updated_at"]
    stale = datetime(2020, 1, 1, tzinfo=timezone.utc)

    assert repository.update(created["id"], owner_id, {"name": "Wrong version"}, expected_updated_at=stale) is None
    updated = repository.update(created["id"], owner_id, {"name": "Updated Njoro Farm"}, expected_updated_at=current)
    assert updated["name"] == "Updated Njoro Farm"
