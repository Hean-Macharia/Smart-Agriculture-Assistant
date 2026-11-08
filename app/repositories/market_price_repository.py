from datetime import date, datetime, time, timezone

from bson import ObjectId
from pymongo.collection import Collection

from app.repositories.farmer_repository import public_document


class MarketPriceRepository:
    """Market observations are append-only; revisions retain the old observation."""

    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index([("crop_name", 1), ("county", 1), ("date_collected", -1)], name="ix_prices_crop_county_date")
        self.collection.create_index([("market_location", 1), ("created_at", -1)], name="ix_prices_market_created")

    @staticmethod
    def _public(doc):
        if doc is None:
            return None
        result = public_document(doc)
        for field in ("recorded_by", "supersedes_id"):
            if result.get(field) is not None:
                result[field] = str(result[field])
        if isinstance(result.get("date_collected"), datetime):
            result["date_collected"] = result["date_collected"].date()
        return result

    @staticmethod
    def _to_doc(values: dict):
        result = dict(values)
        collected = result.get("date_collected")
        if isinstance(collected, date) and not isinstance(collected, datetime):
            result["date_collected"] = datetime.combine(collected, time.min, tzinfo=timezone.utc)
        if result.get("recorded_by"):
            result["recorded_by"] = ObjectId(result["recorded_by"])
        if result.get("supersedes_id"):
            result["supersedes_id"] = ObjectId(result["supersedes_id"])
        return result

    def create(self, values: dict):
        doc = self._to_doc(values)
        doc["created_at"] = datetime.now(timezone.utc)
        result = self.collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return self._public(doc)

    def get(self, price_id: str):
        try:
            return self._public(self.collection.find_one({"_id": ObjectId(price_id)}))
        except Exception as exc:
            if isinstance(exc, (ValueError, TypeError)):
                return None
            raise

    def create_revision(self, price_id: str, recorded_by: str, changes: dict):
        previous = self.get(price_id)
        if previous is None:
            return None
        values = {k: previous[k] for k in ("crop_name", "market_location", "county", "unit", "data_source", "source_name")}
        values.update(changes)
        values.update(recorded_by=recorded_by, supersedes_id=price_id)
        return self.create(values)

    def list_prices(self, *, crop_name: str | None, county: str | None, market_location: str | None, start_date: date | None, end_date: date | None, skip: int, limit: int):
        query = {}
        if crop_name:
            query["crop_name"] = {"$regex": f"^{_escape(crop_name)}$", "$options": "i"}
        if county:
            query["county"] = {"$regex": f"^{_escape(county)}$", "$options": "i"}
        if market_location:
            query["market_location"] = {"$regex": f"^{_escape(market_location)}$", "$options": "i"}
        if start_date or end_date:
            query["date_collected"] = {}
            if start_date:
                query["date_collected"]["$gte"] = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
            if end_date:
                query["date_collected"]["$lt"] = datetime.combine(date.fromordinal(end_date.toordinal() + 1), time.min, tzinfo=timezone.utc)
        total = self.collection.count_documents(query)
        cursor = self.collection.find(query).sort([("date_collected", -1), ("created_at", -1)]).skip(skip).limit(limit)
        return [self._public(doc) for doc in cursor], total

    def compare(self, *, crop_name: str, county: str | None):
        query = {"crop_name": {"$regex": f"^{_escape(crop_name)}$", "$options": "i"}}
        if county:
            query["county"] = {"$regex": f"^{_escape(county)}$", "$options": "i"}
        docs = self.collection.find(query).sort([("date_collected", -1), ("created_at", -1)])
        latest = {}
        for doc in docs:
            key = (doc["county"].casefold(), doc["market_location"].casefold(), doc["unit"].casefold())
            latest.setdefault(key, self._public(doc))
        return sorted(latest.values(), key=lambda d: (d["county"].casefold(), d["market_location"].casefold()))


def _escape(value: str) -> str:
    import re

    return re.escape(value.strip())
