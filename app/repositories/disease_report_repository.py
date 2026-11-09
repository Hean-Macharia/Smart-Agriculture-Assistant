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
        return result

    def create(self, values: dict):
        doc = {**values, "farmer_id": ObjectId(values["farmer_id"]), "created_at": datetime.now(timezone.utc)}
        inserted = self.collection.insert_one(doc)
        doc["_id"] = inserted.inserted_id
        return self._public(doc)

    def list_for_farmer(self, farmer_id: str, *, skip: int, limit: int):
        query = {"farmer_id": ObjectId(farmer_id)}
        total = self.collection.count_documents(query)
        docs = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(doc) for doc in docs], total
