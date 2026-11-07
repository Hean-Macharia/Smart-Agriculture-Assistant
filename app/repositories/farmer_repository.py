from bson import ObjectId
from pymongo.collection import Collection


def public_document(document: dict | None) -> dict | None:
    if document is None:
        return None
    result = dict(document)
    result["id"] = str(result.pop("_id"))
    result.pop("_internal_user_id", None)
    for key in ("owner_id", "user_id", "farmer_id"):
        if key in result:
            result[key] = str(result[key])
    return result


class FarmerRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index("user_id", unique=True, name="uq_farmer_profile_user")

    def get_profile(self, user_id: str) -> dict | None:
        return public_document(self.collection.find_one({"user_id": ObjectId(user_id)}))

    def upsert_profile(self, user_id: str, values: dict) -> dict:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        self.collection.update_one(
            {"user_id": ObjectId(user_id)},
            {"$set": {**values, "updated_at": now}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return public_document(self.collection.find_one({"user_id": ObjectId(user_id)}))
