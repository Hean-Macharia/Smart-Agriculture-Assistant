import re
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection

from app.models.marketplace import ProductAvailability
from app.repositories.farmer_repository import public_document


class MarketplaceRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index([("farmer_id", 1), ("is_active", 1)], name="ix_products_farmer_active")
        self.collection.create_index([("availability_status", 1), ("county", 1), ("category", 1)], name="ix_products_browse")
        self.collection.create_index([("created_at", -1)], name="ix_products_created")

    def create(self, farmer_id: str, values: dict) -> dict:
        now = datetime.now(timezone.utc)
        document = {
            **values,
            "farmer_id": ObjectId(farmer_id),
            "availability_status": ProductAvailability.ACTIVE.value,
            "is_active": True,
            "_stock_reservations": [],
            "created_at": now,
            "updated_at": now,
        }
        result = self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return self._public(document)

    @staticmethod
    def _public(document: dict | None) -> dict | None:
        if document is None:
            return None
        result = public_document(document)
        result.pop("_stock_reservations", None)
        result.pop("is_active", None)
        return result

    def get(self, product_id: str, *, active_only: bool = True) -> dict | None:
        query = {"_id": ObjectId(product_id)}
        if active_only:
            query.update(is_active=True, availability_status={"$in": ["ACTIVE", "SOLD_OUT"]})
        return self._public(self.collection.find_one(query))

    def list_products(
        self,
        *,
        search: str | None,
        county: str | None,
        category: str | None,
        min_price: int | None,
        max_price: int | None,
        skip: int,
        limit: int,
    ) -> tuple[list[dict], int]:
        query: dict = {"is_active": True, "availability_status": "ACTIVE", "quantity_available": {"$gt": 0}}
        if search:
            query["product_name"] = {"$regex": re.escape(search.strip()), "$options": "i"}
        if county:
            query["county"] = {"$regex": f"^{re.escape(county.strip())}$", "$options": "i"}
        if category:
            query["category"] = {"$regex": f"^{re.escape(category.strip())}$", "$options": "i"}
        price: dict[str, int] = {}
        if min_price is not None:
            price["$gte"] = min_price
        if max_price is not None:
            price["$lte"] = max_price
        if price:
            query["price_per_unit_kes"] = price
        total = self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(doc) for doc in cursor], total

    def list_for_farmer(self, farmer_id: str, *, skip: int, limit: int) -> tuple[list[dict], int]:
        query = {"farmer_id": ObjectId(farmer_id), "is_active": True}
        total = self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(doc) for doc in cursor], total

    def update(self, product_id: str, farmer_id: str, changes: dict) -> dict | None:
        query = {"_id": ObjectId(product_id), "farmer_id": ObjectId(farmer_id), "is_active": True}
        if "quantity_available" in changes:
            current = self.collection.find_one(query, {"quantity_available": 1})
            if current is None:
                return None
            changes = dict(changes)
            changes["availability_status"] = "ACTIVE" if changes["quantity_available"] > 0 else "SOLD_OUT"
            query["quantity_available"] = current["quantity_available"]
        result = self.collection.update_one(query, {"$set": {**changes, "updated_at": datetime.now(timezone.utc)}})
        if result.matched_count != 1:
            return None
        doc = self.collection.find_one({"_id": ObjectId(product_id), "farmer_id": ObjectId(farmer_id), "is_active": True})
        return self._public(doc)

    def deactivate(self, product_id: str, farmer_id: str) -> bool:
        result = self.collection.update_one(
            {"_id": ObjectId(product_id), "farmer_id": ObjectId(farmer_id), "is_active": True},
            {"$set": {"is_active": False, "availability_status": "INACTIVE", "updated_at": datetime.now(timezone.utc)}},
        )
        return result.modified_count == 1

    def reserve_stock(self, product_id: str, quantity: int, order_id: str) -> dict | None:
        order_object_id = ObjectId(order_id)
        updated = self.collection.find_one_and_update(
            {
                "_id": ObjectId(product_id),
                "is_active": True,
                "availability_status": "ACTIVE",
                "quantity_available": {"$gte": quantity},
            },
            {
                "$inc": {"quantity_available": -quantity},
                "$addToSet": {"_stock_reservations": order_object_id},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated and updated["quantity_available"] == 0:
            self.collection.update_one(
                {"_id": updated["_id"], "quantity_available": 0},
                {"$set": {"availability_status": "SOLD_OUT"}},
            )
            updated["availability_status"] = "SOLD_OUT"
        return self._public(updated)

    def release_stock(self, product_id: str, quantity: int, order_id: str) -> bool:
        order_object_id = ObjectId(order_id)
        updated = self.collection.find_one_and_update(
            {"_id": ObjectId(product_id), "_stock_reservations": order_object_id},
            {
                "$inc": {"quantity_available": quantity},
                "$pull": {"_stock_reservations": order_object_id},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated and updated["is_active"] and updated["quantity_available"] > 0:
            self.collection.update_one(
                {"_id": updated["_id"], "is_active": True, "quantity_available": updated["quantity_available"]},
                {"$set": {"availability_status": "ACTIVE"}},
            )
        return updated is not None
