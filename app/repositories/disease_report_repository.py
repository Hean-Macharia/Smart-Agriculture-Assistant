from datetime import datetime, timezone

from bson import ObjectId
from pymongo.collection import Collection

from app.repositories.farmer_repository import public_document


class DiseaseReportRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index([("farmer_id", 1), ("created_at", -1)], name="ix_disease_reports_farmer_created")

    @staticmethod
    def _public(doc):
        result = public_document(doc)
        if result:
            result["farmer_id"] = str(result["farmer_id"])
            for review in result.get("officer_reviews", []):
                review["officer_id"] = str(review["officer_id"])
        return result

    def create(self, values: dict):
        doc = {**values, "farmer_id": ObjectId(values["farmer_id"]), "created_at": datetime.now(timezone.utc)}
        inserted = self.collection.insert_one(doc)
        doc["_id"] = inserted.inserted_id
        return self._public(doc)

    def get_for_farmer(self, report_id: str, farmer_id: str):
        if not ObjectId.is_valid(report_id) or not ObjectId.is_valid(farmer_id):
            return None
        return self._public(self.collection.find_one({"_id": ObjectId(report_id), "farmer_id": ObjectId(farmer_id)}))

    def request_review(self, report_id: str, farmer_id: str):
        if not ObjectId.is_valid(report_id) or not ObjectId.is_valid(farmer_id):
            return None
        now = datetime.now(timezone.utc)
        updated = self.collection.find_one_and_update(
            {
                "_id": ObjectId(report_id),
                "farmer_id": ObjectId(farmer_id),
                "case_status": {"$in": [None, "OPEN"]},
            },
            {"$set": {"case_status": "REVIEW_REQUESTED", "review_requested_at": now, "updated_at": now}},
            return_document=True,
        )
        return self._public(updated)

    def resolve(self, report_id: str, farmer_id: str):
        if not ObjectId.is_valid(report_id) or not ObjectId.is_valid(farmer_id):
            return None
        now = datetime.now(timezone.utc)
        updated = self.collection.find_one_and_update(
            {
                "_id": ObjectId(report_id),
                "farmer_id": ObjectId(farmer_id),
                "case_status": {"$in": [None, "OPEN", "REVIEW_REQUESTED"]},
            },
            {"$set": {"case_status": "RESOLVED", "resolved_at": now, "updated_at": now}},
            return_document=True,
        )
        return self._public(updated)

    def list_review_requested(self, *, skip: int, limit: int):
        query = {"case_status": "REVIEW_REQUESTED"}
        total = self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("review_requested_at", 1).skip(skip).limit(limit)
        return [self._public(doc) for doc in cursor], total

    def record_officer_review(self, report_id: str, officer_id: str, note: str):
        if not ObjectId.is_valid(report_id) or not ObjectId.is_valid(officer_id):
            return None
        now = datetime.now(timezone.utc)
        updated = self.collection.find_one_and_update(
            {"_id": ObjectId(report_id), "case_status": "REVIEW_REQUESTED"},
            {
                "$push": {"officer_reviews": {"officer_id": ObjectId(officer_id), "note": note, "at": now}},
                "$set": {"case_status": "OPEN", "updated_at": now},
            },
            return_document=True,
        )
        return self._public(updated)

    def list_for_farmer(self, farmer_id: str, *, skip: int, limit: int):
        query = {"farmer_id": ObjectId(farmer_id)}
        total = self.collection.count_documents(query)
        docs = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(doc) for doc in docs], total
