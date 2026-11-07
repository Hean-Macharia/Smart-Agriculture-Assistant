from datetime import datetime, timezone

from bson import ObjectId
from pymongo.collection import Collection

from app.repositories.farmer_repository import public_document


class CropRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index([("farm_id", 1), ("is_active", 1)], name="ix_crops_farm_active")
        self.collection.create_index([("owner_id", 1), ("created_at", -1)], name="ix_crops_owner_created")

    def create(self, owner_id: str, values: dict) -> dict:
        now = datetime.now(timezone.utc)
        document = {
            **values,
            "farm_id": ObjectId(values["farm_id"]),
            "owner_id": ObjectId(owner_id),
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        result = self.collection.insert_one(document)
        document["_id"] = result.inserted_id
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

    def update(self, crop_id: str, owner_id: str, changes: dict) -> dict | None:
        query = {"_id": ObjectId(crop_id), "owner_id": ObjectId(owner_id), "is_active": True}
        if not self.collection.find_one(query):
            return None
        self.collection.update_one(query, {"$set": {**changes, "updated_at": datetime.now(timezone.utc)}})
        return self.get(crop_id)

    def deactivate(self, crop_id: str, owner_id: str) -> bool:
        result = self.collection.update_one(
            {"_id": ObjectId(crop_id), "owner_id": ObjectId(owner_id), "is_active": True},
            {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}},
        )
        return result.modified_count == 1
