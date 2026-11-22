from datetime import datetime, timezone

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from app.repositories.farmer_repository import public_document


class FollowupIdempotencyConflict(Exception):
    """A follow-up idempotency key was reused for another report."""


class DiseaseFollowupRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index([("disease_report_id", 1), ("created_at", 1)], name="ix_followups_report_created")
        self.collection.create_index("idempotency_key", unique=True, name="uq_followups_idempotency")

    @staticmethod
    def _public(document):
        result = public_document(document)
        if result is None:
            return None
        result["farmer_id"] = str(result["farmer_id"])
        result["disease_report_id"] = str(result["disease_report_id"])
        return result

    def get_by_idempotency_key(self, key: str):
        return self._public(self.collection.find_one({"idempotency_key": key}))

    def create(self, values: dict):
        report_id = ObjectId(values["disease_report_id"])
        farmer_id = ObjectId(values["farmer_id"])
        key = values["idempotency_key"]
        prior = self.collection.find_one({"idempotency_key": key})
        if prior:
            if prior["disease_report_id"] == report_id and prior["farmer_id"] == farmer_id:
                return self._public(prior), False
            raise FollowupIdempotencyConflict

        document = {
            **values,
            "disease_report_id": report_id,
            "farmer_id": farmer_id,
            "created_at": datetime.now(timezone.utc),
        }
        try:
            result = self.collection.insert_one(document)
        except DuplicateKeyError:
            prior = self.collection.find_one({"idempotency_key": key})
            if prior and prior["disease_report_id"] == report_id and prior["farmer_id"] == farmer_id:
                return self._public(prior), False
            raise FollowupIdempotencyConflict from None
        document["_id"] = result.inserted_id
        return self._public(document), True

    def list_for_report(self, report_id: str, farmer_id: str):
        if not ObjectId.is_valid(report_id) or not ObjectId.is_valid(farmer_id):
            return []
        cursor = self.collection.find({
            "disease_report_id": ObjectId(report_id),
            "farmer_id": ObjectId(farmer_id),
        }).sort("created_at", 1)
        return [self._public(document) for document in cursor]
