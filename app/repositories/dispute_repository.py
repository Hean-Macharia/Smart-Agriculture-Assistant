from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from app.repositories.farmer_repository import public_document


class DisputeRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index("order_id", unique=True, name="uq_dispute_order")
        self.collection.create_index([("raised_by", 1), ("created_at", -1)], name="ix_dispute_user_created")

    @staticmethod
    def _public(doc):
        if doc is None:
            return None
        result = public_document(doc)
        for field in ("order_id", "buyer_id", "seller_id", "raised_by"):
            result[field] = str(result[field])
        result["evidence_urls"] = [str(url) for url in result.get("evidence_urls", [])]
        for decision in result.get("decisions", []):
            decision["admin_id"] = str(decision["admin_id"])
        return result

    def create(self, values: dict):
        now = datetime.now(timezone.utc)
        doc = {**values, "order_id": ObjectId(values["order_id"]), "buyer_id": ObjectId(values["buyer_id"]), "seller_id": ObjectId(values["seller_id"]), "raised_by": ObjectId(values["raised_by"]), "status": "OPEN", "decisions": [], "created_at": now, "updated_at": now}
        try:
            result = self.collection.insert_one(doc)
        except DuplicateKeyError as exc:
            raise ValueError("A dispute already exists for this order") from exc
        doc["_id"] = result.inserted_id
        return self._public(doc)

    def get(self, dispute_id: str):
        return self._public(self.collection.find_one({"_id": ObjectId(dispute_id)}))

    def list_for_user(self, user_id: str, *, skip: int, limit: int):
        oid = ObjectId(user_id)
        query = {"$or": [{"buyer_id": oid}, {"seller_id": oid}]}
        total = self.collection.count_documents(query)
        docs = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(d) for d in docs], total

    def list_all(self, *, skip: int, limit: int):
        total = self.collection.count_documents({})
        docs = self.collection.find({}).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(d) for d in docs], total

    def review(self, dispute_id: str, *, status: str, admin_id: str, resolution: str, decision: str | None, allowed_current: list[str] | None = None):
        now = datetime.now(timezone.utc)
        audit = {"admin_id": ObjectId(admin_id), "status": status, "decision": decision, "resolution": resolution, "at": now}
        doc = self.collection.find_one_and_update(
            {"_id": ObjectId(dispute_id), "status": {"$in": allowed_current or ["OPEN", "UNDER_REVIEW"]}},
            {"$set": {"status": status, "updated_at": now}, "$push": {"decisions": audit}},
            return_document=ReturnDocument.AFTER,
        )
        return self._public(doc)
