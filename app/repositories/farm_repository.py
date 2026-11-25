from datetime import datetime, timezone
import hashlib
import json

from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from pymongo.collection import Collection

from app.repositories.farmer_repository import public_document


class FarmRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index([("owner_id", 1), ("is_active", 1)], name="ix_farms_owner_active")
        self.collection.create_index(
            [("owner_id", 1), ("_client_operation_id", 1)],
            name="uq_farms_client_operation",
            unique=True,
            partialFilterExpression={"_client_operation_id": {"$type": "string"}},
        )

    def create(self, owner_id: str, values: dict, *, idempotency_key: str | None = None) -> dict:
        # MongoDB BSON dates have millisecond precision. Return matching
        # precision so a just-created resource can be safely updated with
        # the timestamp returned to an offline client in If-Match.
        now = datetime.now(timezone.utc)
        now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
        document = {**values, "owner_id": ObjectId(owner_id), "is_active": True, "created_at": now, "updated_at": now}
        operation_hash = hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()
        if idempotency_key:
            query = {"owner_id": ObjectId(owner_id), "_client_operation_id": idempotency_key}
            existing = self.collection.find_one(query)
            if existing:
                if existing.get("_client_operation_hash") != operation_hash:
                    raise ValueError("Idempotency-Key was already used with a different request")
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
            return public_document(existing)
        document["_id"] = result.inserted_id
        return public_document(document)

    def get(self, farm_id: str, *, active_only: bool = True) -> dict | None:
        query = {"_id": ObjectId(farm_id)}
        if active_only:
            query["is_active"] = True
        return public_document(self.collection.find_one(query))

    def list_for_owner(self, owner_id: str, *, skip: int, limit: int) -> tuple[list[dict], int]:
        query = {"owner_id": ObjectId(owner_id), "is_active": True}
        total = self.collection.count_documents(query)
        docs = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [public_document(doc) for doc in docs], total

    def update(self, farm_id: str, owner_id: str, changes: dict, *, expected_updated_at: datetime | None = None) -> dict | None:
        query = {"_id": ObjectId(farm_id), "owner_id": ObjectId(owner_id), "is_active": True}
        if expected_updated_at is not None:
            query["updated_at"] = expected_updated_at
        if not self.collection.find_one(query):
            return None
        result = self.collection.update_one(query, {"$set": {**changes, "updated_at": datetime.now(timezone.utc)}})
        if result.modified_count != 1:
            return None
        identity = {"_id": ObjectId(farm_id), "owner_id": ObjectId(owner_id), "is_active": True}
        return public_document(self.collection.find_one(identity))

    def deactivate(self, farm_id: str, owner_id: str) -> bool:
        result = self.collection.update_one(
            {"_id": ObjectId(farm_id), "owner_id": ObjectId(owner_id), "is_active": True},
            {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}},
        )
        return result.modified_count == 1
