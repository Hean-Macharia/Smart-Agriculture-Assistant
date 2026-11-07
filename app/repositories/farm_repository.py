from datetime import datetime, timezone

from bson import ObjectId
from pymongo.collection import Collection

from app.repositories.farmer_repository import public_document


class FarmRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index([("owner_id", 1), ("is_active", 1)], name="ix_farms_owner_active")

    def create(self, owner_id: str, values: dict) -> dict:
        now = datetime.now(timezone.utc)
        document = {**values, "owner_id": ObjectId(owner_id), "is_active": True, "created_at": now, "updated_at": now}
        result = self.collection.insert_one(document)
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

    def update(self, farm_id: str, owner_id: str, changes: dict) -> dict | None:
        query = {"_id": ObjectId(farm_id), "owner_id": ObjectId(owner_id), "is_active": True}
        if not self.collection.find_one(query):
            return None
        self.collection.update_one(query, {"$set": {**changes, "updated_at": datetime.now(timezone.utc)}})
        return public_document(self.collection.find_one(query))

    def deactivate(self, farm_id: str, owner_id: str) -> bool:
        result = self.collection.update_one(
            {"_id": ObjectId(farm_id), "owner_id": ObjectId(owner_id), "is_active": True},
            {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}},
        )
        return result.modified_count == 1
