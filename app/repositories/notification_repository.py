from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from app.repositories.farmer_repository import public_document


class NotificationRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index("idempotency_key", unique=True, name="uq_notification_idempotency")
        self.collection.create_index([("recipient_user_id", 1), ("created_at", -1)], name="ix_notifications_recipient_created")

    @staticmethod
    def _public(doc):
        if doc is None:
            return None
        result = public_document(doc)
        result["recipient_user_id"] = str(result["recipient_user_id"])
        result.pop("recipient_phone", None)
        result.pop("idempotency_key", None)
        return result

    def create_pending(self, values: dict):
        doc = {**values, "recipient_user_id": ObjectId(values["recipient_user_id"]), "status": "PENDING", "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
        try:
            result = self.collection.insert_one(doc)
            doc["_id"] = result.inserted_id
            return self._public(doc), True
        except DuplicateKeyError:
            prior = self.collection.find_one({"idempotency_key": values["idempotency_key"]})
            expected = {**values, "recipient_user_id": ObjectId(values["recipient_user_id"])}
            if prior is None or any(prior.get(key) != expected.get(key) for key in ("recipient_user_id", "event", "message", "recipient_phone")):
                raise ValueError("Idempotency key was already used for a different notification")
            return self._public(prior), False

    def claim(self, notification_id: str):
        doc = self.collection.find_one_and_update({"_id": ObjectId(notification_id), "status": "PENDING"}, {"$set": {"status": "SENDING", "updated_at": datetime.now(timezone.utc)}}, return_document=ReturnDocument.AFTER)
        return self._public(doc)

    def finish(self, notification_id: str, *, status: str, provider_reference: str | None):
        doc = self.collection.find_one_and_update({"_id": ObjectId(notification_id), "status": "SENDING"}, {"$set": {"status": status, "provider_reference": provider_reference, "updated_at": datetime.now(timezone.utc)}}, return_document=ReturnDocument.AFTER)
        return self._public(doc)

    def get(self, notification_id: str):
        return self._public(self.collection.find_one({"_id": ObjectId(notification_id)}))

    def list_for_user(self, user_id: str, *, skip: int, limit: int):
        query = {"recipient_user_id": ObjectId(user_id)}
        total = self.collection.count_documents(query)
        docs = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(doc) for doc in docs], total
