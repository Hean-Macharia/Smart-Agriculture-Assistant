from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection

from app.repositories.farmer_repository import public_document


class OrderRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index([("buyer_id", 1), ("created_at", -1)], name="ix_orders_buyer_created")
        self.collection.create_index([("seller_id", 1), ("created_at", -1)], name="ix_orders_seller_created")
        self.collection.create_index("product_id", name="ix_orders_product")

    @staticmethod
    def _public(document: dict | None) -> dict | None:
        if document is None:
            return None
        result = public_document(document)
        for key in ("buyer_id", "seller_id", "product_id"):
            result[key] = str(result[key])
        if result.get("payment_id") is not None:
            result["payment_id"] = str(result["payment_id"])
        result.pop("_stock_reservation_released", None)
        return result

    def create(self, values: dict) -> dict:
        now = datetime.now(timezone.utc)
        document = {**values, "created_at": now, "updated_at": now, "_stock_reservation_released": False}
        for key in ("buyer_id", "seller_id", "product_id"):
            document[key] = ObjectId(document[key])
        result = self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return self._public(document)

    def get(self, order_id: str) -> dict | None:
        return self._public(self.collection.find_one({"_id": ObjectId(order_id)}))

    def list_for_user(self, field: str, user_id: str, *, skip: int, limit: int) -> tuple[list[dict], int]:
        query = {field: ObjectId(user_id)}
        total = self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(doc) for doc in cursor], total

    def transition(self, order_id: str, allowed_current: list[str], target: str) -> dict | None:
        return self._public(
            self.collection.find_one_and_update(
                {"_id": ObjectId(order_id), "order_status": {"$in": allowed_current}},
                {"$set": {"order_status": target, "updated_at": datetime.now(timezone.utc)}},
                return_document=ReturnDocument.AFTER,
            )
        )

    def mark_paid(self, order_id: str, payment_id: str) -> dict | None:
        updated = self.collection.find_one_and_update(
            {"_id": ObjectId(order_id), "order_status": "AWAITING_PAYMENT", "payment_status": "UNPAID"},
            {
                "$set": {
                    "order_status": "PAID",
                    "payment_status": "PAID",
                    "payment_id": ObjectId(payment_id),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated:
            return self._public(updated)
        existing = self.collection.find_one({"_id": ObjectId(order_id)})
        if existing and existing.get("order_status") == "PAID" and str(existing.get("payment_id")) == payment_id:
            return self._public(existing)
        return None
