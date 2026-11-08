from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection

from app.repositories.farmer_repository import public_document


class AdvisoryRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index([("farmer_id", 1), ("created_at", -1)], name="ix_advisories_farmer_created")
        self.collection.create_index([("kind", 1), ("is_active", 1), ("crop_name", 1), ("county", 1)], name="ix_advisories_scope")

    @staticmethod
    def _public(doc):
        if doc is None:
            return None
        result = public_document(doc)
        for key in ("farm_id", "farmer_id", "author_id"):
            if result.get(key) is not None:
                result[key] = str(result[key])
        return result

    def create(self, values: dict):
        doc = dict(values)
        for key in ("farm_id", "farmer_id", "author_id"):
            if doc.get(key):
                doc[key] = ObjectId(doc[key])
        now = datetime.now(timezone.utc)
        doc.update(created_at=now, updated_at=now)
        result = self.collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return self._public(doc)

    def get(self, advisory_id: str):
        return self._public(self.collection.find_one({"_id": ObjectId(advisory_id)}))

    def list_for_farmer(self, *, farmer_id: str, crop_name: str | None, county: str | None, skip: int, limit: int):
        officer_query = {"kind": "OFFICER", "is_active": True}
        if crop_name:
            officer_query["$or"] = [{"crop_name": None}, {"crop_name": {"$regex": f"^{_escape(crop_name)}$", "$options": "i"}}]
        if county:
            officer_query["$and"] = officer_query.get("$and", []) + [{"$or": [{"county": None}, {"county": {"$regex": f"^{_escape(county)}$", "$options": "i"}}]}]
        query = {"$or": [officer_query, {"kind": "WEATHER_RULE", "farmer_id": ObjectId(farmer_id)}]}
        total = self.collection.count_documents(query)
        docs = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(doc) for doc in docs], total

    def list_all(self, *, skip: int, limit: int, active_only: bool = True):
        query = {"kind": "OFFICER"}
        if active_only:
            query["is_active"] = True
        total = self.collection.count_documents(query)
        docs = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(doc) for doc in docs], total

    def list_for_farmer_history(self, farmer_id: str, *, skip: int, limit: int):
        query = {"farmer_id": ObjectId(farmer_id)}
        total = self.collection.count_documents(query)
        docs = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(doc) for doc in docs], total

    def update_officer(self, advisory_id: str, author_id: str, changes: dict, *, is_admin: bool):
        query = {"_id": ObjectId(advisory_id), "kind": "OFFICER"}
        if not is_admin:
            query["author_id"] = ObjectId(author_id)
        doc = self.collection.find_one_and_update(query, {"$set": {**changes, "updated_at": datetime.now(timezone.utc)}}, return_document=ReturnDocument.AFTER)
        return self._public(doc)


def _escape(value: str) -> str:
    import re

    return re.escape(value.strip())
