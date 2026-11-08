from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection

from app.repositories.farmer_repository import public_document


class DeliveryRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index("order_id", unique=True, name="uq_delivery_order")
        self.collection.create_index([("buyer_id", 1), ("created_at", -1)], name="ix_delivery_buyer_created")
        self.collection.create_index([("seller_id", 1), ("created_at", -1)], name="ix_delivery_seller_created")

    @staticmethod
    def _public(doc):
        if doc is None:
            return None
        result = public_document(doc)
        for field in ("order_id", "buyer_id", "seller_id"):
            result[field] = str(result[field])
        for event in result.get("events", []):
            if event.get("by") is not None:
                event["by"] = str(event["by"])
        return result

    def create(self, values: dict) -> dict:
        now = datetime.now(timezone.utc)
        doc = {**values, "order_id": ObjectId(values["order_id"]), "buyer_id": ObjectId(values["buyer_id"]), "seller_id": ObjectId(values["seller_id"]), "status": "PENDING", "events": [{"status": "PENDING", "at": now, "by": values["seller_id"], "note": "Delivery created"}], "created_at": now, "updated_at": now}
        try:
            inserted = self.collection.insert_one(doc)
            doc["_id"] = inserted.inserted_id
            return self._public(doc)
        except Exception:
            saved = self.collection.find_one({"order_id": ObjectId(values["order_id"])})
            if saved:
                return self._public(saved)
            raise

    def get(self, delivery_id: str) -> dict | None:
        return self._public(self.collection.find_one({"_id": ObjectId(delivery_id)}))

    def get_by_order(self, order_id: str) -> dict | None:
        return self._public(self.collection.find_one({"order_id": ObjectId(order_id)}))

    def list_for_user(self, field: str, user_id: str, *, skip: int, limit: int):
        query = {field: ObjectId(user_id)}
        total = self.collection.count_documents(query)
        docs = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(d) for d in docs], total

    def transition(self, delivery_id: str, allowed: list[str], target: str, actor_id: str, note: str | None):
        now = datetime.now(timezone.utc)
        doc = self.collection.find_one_and_update(
            {"_id": ObjectId(delivery_id), "status": {"$in": allowed}},
            {"$set": {"status": target, "updated_at": now}, "$push": {"events": {"status": target, "at": now, "by": ObjectId(actor_id), "note": note}}},
            return_document=ReturnDocument.AFTER,
        )
        return self._public(doc)
