from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from app.repositories.farmer_repository import public_document


class EscrowRepository:
    def __init__(self, collection: Collection, disputes: Collection):
        self.collection = collection
        self.disputes = disputes
        self.collection.create_index("order_id", unique=True, name="uq_escrow_order")
        self.collection.create_index("payment_id", unique=True, name="uq_escrow_payment")

    @staticmethod
    def _public(document: dict | None) -> dict | None:
        if document is None:
            return None
        result = public_document(document)
        for key in ("order_id", "payment_id"):
            result[key] = str(result[key])
        return result

    def create_for_payment(self, values: dict) -> dict:
        now = datetime.now(timezone.utc)
        document = {
            **values,
            "order_id": ObjectId(values["order_id"]),
            "payment_id": ObjectId(values["payment_id"]),
            "status": values.get("status", "PAYMENT_RECEIVED"),
            "custody_status": values.get("custody_status", "NOT_SAFEGUARDED"),
            "actual_funds_safeguarded": values.get("actual_funds_safeguarded", False),
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = self.collection.insert_one(document)
            document["_id"] = result.inserted_id
            return self._public(document)
        except DuplicateKeyError:
            return self._public(self.collection.find_one({"payment_id": ObjectId(values["payment_id"])}))

    def get(self, escrow_id: str) -> dict | None:
        return self._public(self.collection.find_one({"_id": ObjectId(escrow_id)}))

    def get_by_order(self, order_id: str) -> dict | None:
        return self._public(self.collection.find_one({"order_id": ObjectId(order_id)}))

    def transition(self, escrow_id: str, allowed: list[str], target: str, changes: dict | None = None) -> dict | None:
        update = {**(changes or {}), "status": target, "updated_at": datetime.now(timezone.utc)}
        doc = self.collection.find_one_and_update(
            {"_id": ObjectId(escrow_id), "status": {"$in": allowed}},
            {"$set": update},
            return_document=ReturnDocument.AFTER,
        )
        return self._public(doc)

    def has_unresolved_dispute(self, order_id: str) -> bool:
        return self.disputes.count_documents({"order_id": ObjectId(order_id), "status": {"$in": ["OPEN", "UNDER_REVIEW"]}}, limit=1) > 0
