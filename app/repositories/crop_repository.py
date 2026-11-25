from datetime import datetime, timezone
import hashlib
import json

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from app.repositories.farmer_repository import public_document


class CropRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index([("farm_id", 1), ("is_active", 1)], name="ix_crops_farm_active")
        self.collection.create_index([("owner_id", 1), ("created_at", -1)], name="ix_crops_owner_created")
        self.collection.create_index(
            [("owner_id", 1), ("_client_operation_id", 1)],
            name="uq_crops_client_operation",
            unique=True,
            partialFilterExpression={"_client_operation_id": {"$type": "string"}},
        )

    def create(self, owner_id: str, values: dict, *, idempotency_key: str | None = None) -> dict:
        # MongoDB BSON dates have millisecond precision; keep the returned
        # timestamp identical to the value used for optimistic concurrency.
        now = datetime.now(timezone.utc)
        now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
        document = {
            **values,
            "farm_id": ObjectId(values["farm_id"]),
            "owner_id": ObjectId(owner_id),
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        operation_hash = hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()
        if idempotency_key:
            query = {"owner_id": ObjectId(owner_id), "_client_operation_id": idempotency_key}
            existing = self.collection.find_one(query)
            if existing:
                if existing.get("_client_operation_hash") != operation_hash:
                    raise ValueError("Idempotency-Key was already used with a different request")
                existing["farm_id"] = str(existing["farm_id"])
                return public_document(existing)
            document.update({"_client_operation_id": idempotency_key, "_client_operation_hash": operation_hash})
        try:
            result = self.collection.insert_one(document)
        except DuplicateKeyError:
            if not idempotency_key:
                raise
            existing = self.collection.find_one({"owner_id": ObjectId(owner_id), "_client_operation_id": idempotency_key})
            if not existing or existing.get("_client_operation_hash") != operation_hash:
                raise ValueError("Idempotency-Key was already used with a different request")
            existing["farm_id"] = str(existing["farm_id"])
            return public_document(existing)
        document["_id"] = result.inserted_id
        # The response schema uses string IDs; MongoDB persists references as
        # ObjectIds, so normalize this relationship before returning a newly
        # inserted crop just as get() and list_for_owner() do.
        document["farm_id"] = str(document["farm_id"])
        return public_document(document)

    def get(self, crop_id: str, *, active_only: bool = True) -> dict | None:
        query = {"_id": ObjectId(crop_id)}
        if active_only:
            query["is_active"] = True
        doc = self.collection.find_one(query)
        if doc:
            doc["farm_id"] = str(doc["farm_id"])
        return public_document(doc)

    def list_for_owner(self, owner_id: str, *, farm_id: str | None, skip: int, limit: int) -> tuple[list[dict], int]:
        query = {"owner_id": ObjectId(owner_id), "is_active": True}
        if farm_id:
            query["farm_id"] = ObjectId(farm_id)
        total = self.collection.count_documents(query)
        docs = list(self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit))
        for doc in docs:
            doc["farm_id"] = str(doc["farm_id"])
        return [public_document(doc) for doc in docs], total

    def update(self, crop_id: str, owner_id: str, changes: dict, *, expected_updated_at: datetime | None = None) -> dict | None:
        query = {"_id": ObjectId(crop_id), "owner_id": ObjectId(owner_id), "is_active": True}
        if expected_updated_at is not None:
            query["updated_at"] = expected_updated_at
        if not self.collection.find_one(query):
            return None
        result = self.collection.update_one(query, {"$set": {**changes, "updated_at": datetime.now(timezone.utc)}})
        if result.modified_count != 1:
            return None
        return self.get(crop_id)

    def deactivate(self, crop_id: str, owner_id: str) -> bool:
        result = self.collection.update_one(
            {"_id": ObjectId(crop_id), "owner_id": ObjectId(owner_id), "is_active": True},
            {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}},
        )
        return result.modified_count == 1
