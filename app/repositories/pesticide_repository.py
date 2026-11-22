from datetime import datetime, timezone

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from app.models.pesticide import PesticideReviewDecision, PesticideReviewStatus
from app.repositories.farmer_repository import public_document


class PesticideRegistrationConflict(Exception):
    """A PCPB registration number has already been submitted."""


class PesticideRepository:
    """Stores PCPB evidence drafts and append-only administrator review events."""

    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index("registration_number", unique=True, name="uq_pesticide_registration")
        self.collection.create_index([("review_status", 1), ("updated_at", -1)], name="ix_pesticide_review_status")

    @staticmethod
    def _public(document: dict | None) -> dict | None:
        result = public_document(document)
        if result is None:
            return None
        for key in ("submitted_by",):
            result[key] = str(result[key])
        for event in result.get("review_events", []):
            event["reviewer_id"] = str(event["reviewer_id"])
        return result

    def create_draft(self, submitted_by: str, values: dict) -> dict:
        now = datetime.now(timezone.utc)
        document = {
            **values,
            "registration_number": values["registration_number"].strip().upper(),
            "submitted_by": ObjectId(submitted_by),
            "review_status": PesticideReviewStatus.PENDING_REVIEW.value,
            "review_events": [],
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise PesticideRegistrationConflict from exc
        document["_id"] = result.inserted_id
        return self._public(document)

    def list_records(self, *, skip: int, limit: int, review_status: str | None = None):
        query = {"review_status": review_status} if review_status else {}
        total = self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        return [self._public(document) for document in cursor], total

    def get(self, record_id: str):
        if not ObjectId.is_valid(record_id):
            return None
        return self._public(self.collection.find_one({"_id": ObjectId(record_id)}))

    def review(self, record_id: str, reviewer_id: str, values: dict):
        if not ObjectId.is_valid(record_id):
            return None
        now = datetime.now(timezone.utc)
        decision = PesticideReviewDecision(values["decision"])
        new_status = (
            PesticideReviewStatus.APPROVED.value
            if decision == PesticideReviewDecision.APPROVE
            else PesticideReviewStatus.REJECTED.value
        )
        event = {
            "reviewer_id": ObjectId(reviewer_id),
            "decision": decision.value,
            "note": values["review_note"],
            "registration_and_label_verified": values["registration_and_label_verified"],
            "source_checked_on": values["source_checked_on"],
            "at": now,
        }
        updated = self.collection.find_one_and_update(
            {"_id": ObjectId(record_id), "review_status": PesticideReviewStatus.PENDING_REVIEW.value},
            {
                "$set": {"review_status": new_status, "updated_at": now},
                "$push": {"review_events": event},
            },
            return_document=True,
        )
        return self._public(updated)

    def list_approved(self, *, crop_name: str | None, skip: int, limit: int):
        query = {"review_status": PesticideReviewStatus.APPROVED.value}
        if crop_name:
            import re

            query["registered_uses"] = {"$regex": re.escape(crop_name.strip()), "$options": "i"}
        total = self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("trade_name", 1).skip(skip).limit(limit)
        return [self._public(document) for document in cursor], total
