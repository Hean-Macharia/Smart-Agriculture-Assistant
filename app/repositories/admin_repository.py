"""Read-only administrative views and append-only administrative audit events."""

from datetime import datetime, timezone
import re

from bson import ObjectId
from pymongo.database import Database


def _plain(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in {"password_hash", "bootstrap_admin", "idempotency_key", "callback_phone_number", "callback_amount_kes", "merchant_request_id", "active_order_id", "_stock_reservations", "_internal_user_id"}:
                continue
            result["id" if key == "_id" else key] = _plain(item)
        return result
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


class AdminRepository:
    def __init__(self, database: Database):
        self.db = database
        self.db["audit_logs"].create_index([("timestamp", -1)], name="ix_audit_timestamp")
        self.db["audit_logs"].create_index([("actor_id", 1), ("timestamp", -1)], name="ix_audit_actor_timestamp")

    @staticmethod
    def _page(collection, query, *, skip: int, limit: int, sort="created_at"):
        total = collection.count_documents(query)
        rows = collection.find(query).sort(sort, -1).skip(skip).limit(limit)
        return [_plain(row) for row in rows], total

    def list_users(self, *, role: str | None, search: str | None, skip: int, limit: int):
        query = {"role": role} if role else {}
        if search:
            pattern = re.escape(search.strip())
            query["$or"] = [{field: {"$regex": pattern, "$options": "i"}} for field in ("full_name", "email", "phone")]
        total = self.db["users"].count_documents(query)
        rows = self.db["users"].find(query, {"password_hash": 0, "bootstrap_admin": 0}).sort("created_at", -1).skip(skip).limit(limit)
        items = []
        for row in rows:
            items.append({key: _plain(row.get(key)) for key in ("full_name", "email", "phone", "role", "is_active", "created_at", "updated_at") if key in row} | {"id": str(row["_id"])})
        return items, total

    def list_people(self, *, role: str, search: str | None, skip: int, limit: int):
        items, total = self.list_users(role=role, search=search, skip=skip, limit=limit)
        if not items:
            return items, total
        ids = [ObjectId(item["id"]) for item in items]
        profile_name = "farmers" if role == "FARMER" else "buyers" if role == "BUYER" else None
        profiles = {}
        if profile_name:
            profiles = {str(profile["user_id"]): profile for profile in self.db[profile_name].find({"user_id": {"$in": ids}})}
        for item in items:
            user_id = item["id"]
            profile = profiles.get(user_id, {})
            item["profile"] = {key: _plain(profile[key]) for key in ("county", "sub_county", "location", "farm_size_acres", "soil_type", "irrigation_available") if key in profile}
            if role == "FARMER":
                item["farm_count"] = self.db["farms"].count_documents({"owner_id": ObjectId(user_id), "is_active": {"$ne": False}})
                item["crop_count"] = self.db["crops"].count_documents({"owner_id": ObjectId(user_id), "is_active": {"$ne": False}})
                item["disease_report_count"] = self.db["disease_reports"].count_documents({"farmer_id": ObjectId(user_id)})
            elif role == "BUYER":
                item["order_count"] = self.db["orders"].count_documents({"buyer_id": ObjectId(user_id)})
            elif role == "AGRICULTURAL_OFFICER":
                item["advisory_count"] = self.db["advisories"].count_documents({"author_id": ObjectId(user_id), "kind": "OFFICER"})
                item["disease_reviews"] = self.db["disease_reports"].count_documents({"officer_reviews.officer_id": ObjectId(user_id)})
                item["pesticide_submissions"] = self.db["pesticide_records"].count_documents({"submitted_by": ObjectId(user_id)})
        return items, total

    def list_farms(self, *, search: str | None, skip: int, limit: int):
        query = {"latitude": {"$type": "number"}, "longitude": {"$type": "number"}}
        if search:
            pattern = re.escape(search.strip())
            query["$or"] = [{key: {"$regex": pattern, "$options": "i"}} for key in ("name", "county", "sub_county", "location")]
        rows, total = self._page(self.db["farms"], query, skip=skip, limit=limit)
        owners = {ObjectId(row["owner_id"]) for row in rows if ObjectId.is_valid(row.get("owner_id"))}
        users = {str(row["_id"]): row for row in self.db["users"].find({"_id": {"$in": list(owners)}}, {"full_name": 1})} if owners else {}
        for row in rows:
            row["owner"] = _plain(users.get(row.get("owner_id"), {}))
        return rows, total

    def list_products(self, *, search: str | None, county: str | None, active: bool | None, skip: int, limit: int):
        query = {}
        if search:
            pattern = re.escape(search.strip())
            query["$or"] = [{key: {"$regex": pattern, "$options": "i"}} for key in ("product_name", "category")]
        if county:
            query["county"] = {"$regex": f"^{re.escape(county.strip())}$", "$options": "i"}
        if active is not None:
            query["is_active"] = active
        rows, total = self._page(self.db["marketplace_products"], query, skip=skip, limit=limit)
        farmer_ids = {ObjectId(row["farmer_id"]) for row in rows if ObjectId.is_valid(row.get("farmer_id"))}
        farmers = {str(row["_id"]): row for row in self.db["users"].find({"_id": {"$in": list(farmer_ids)}}, {"full_name": 1, "email": 1})} if farmer_ids else {}
        for row in rows:
            row["farmer_id"] = str(row.get("farmer_id", ""))
            row["availability_status"] = row.get("availability_status", "INACTIVE" if not row.get("is_active") else "ACTIVE")
            row["farmer"] = _plain(farmers.get(row["farmer_id"], {}))
        return rows, total

    def list_orders(self, *, status: str | None, skip: int, limit: int):
        query = {"order_status": status} if status else {}
        rows, total = self._page(self.db["orders"], query, skip=skip, limit=limit)
        user_ids = {ObjectId(row[key]) for row in rows for key in ("buyer_id", "seller_id") if ObjectId.is_valid(row.get(key))}
        users = {str(item["_id"]): item for item in self.db["users"].find({"_id": {"$in": list(user_ids)}}, {"full_name": 1, "email": 1})} if user_ids else {}
        product_ids = {ObjectId(row["product_id"]) for row in rows if ObjectId.is_valid(row.get("product_id"))}
        products = {str(item["_id"]): item for item in self.db["marketplace_products"].find({"_id": {"$in": list(product_ids)}}, {"product_name": 1})} if product_ids else {}
        for row in rows:
            row["buyer"] = _plain(users.get(row.get("buyer_id"), {}))
            row["seller"] = _plain(users.get(row.get("seller_id"), {}))
            row["product"] = _plain(products.get(row.get("product_id"), {}))
            # Delivery phone numbers and street/village directions are not needed
            # for platform-level order monitoring.
            row.pop("delivery_information", None)
        return rows, total

    def list_escrows(self, *, status: str | None, skip: int, limit: int):
        return self._page(self.db["escrow_transactions"], {"status": status} if status else {}, skip=skip, limit=limit)

    def list_disease_reports(self, *, status: str | None, search: str | None, skip: int, limit: int):
        query = {"case_status": status} if status else {}
        if search:
            pattern = re.escape(search.strip())
            query["$or"] = [{key: {"$regex": pattern, "$options": "i"}} for key in ("predicted_label", "crop_name")]
        rows, total = self._page(self.db["disease_reports"], query, skip=skip, limit=limit)
        farmer_ids = {ObjectId(row["farmer_id"]) for row in rows if ObjectId.is_valid(row.get("farmer_id"))}
        farmers = {str(item["_id"]): item for item in self.db["users"].find({"_id": {"$in": list(farmer_ids)}}, {"full_name": 1, "email": 1})} if farmer_ids else {}
        for row in rows:
            row["farmer"] = _plain(farmers.get(row.get("farmer_id"), {}))
            report_id = ObjectId(row["id"])
            row["followup_count"] = self.db["disease_followups"].count_documents({"disease_report_id": report_id})
            row["treatment_count"] = self.db["disease_treatments"].count_documents({"disease_report_id": report_id})
        return rows, total

    def list_notifications(self, *, status: str | None, skip: int, limit: int):
        rows, total = self._page(self.db["notifications"], {"status": status} if status else {}, skip=skip, limit=limit)
        recipient_ids = {ObjectId(row["recipient_user_id"]) for row in rows if ObjectId.is_valid(row.get("recipient_user_id"))}
        recipients = {str(row["_id"]): row for row in self.db["users"].find({"_id": {"$in": list(recipient_ids)}}, {"full_name": 1})} if recipient_ids else {}
        for row in rows:
            row["recipient"] = _plain(recipients.get(row.get("recipient_user_id"), {}))
            row.pop("recipient_phone", None)
        return rows, total

    def list_pesticides(self, *, status: str | None, skip: int, limit: int):
        rows, total = self._page(self.db["pesticide_records"], {"review_status": status} if status else {}, skip=skip, limit=limit, sort="updated_at")
        submitter_ids = {ObjectId(row["submitted_by"]) for row in rows if ObjectId.is_valid(row.get("submitted_by"))}
        submitters = {str(row["_id"]): row for row in self.db["users"].find({"_id": {"$in": list(submitter_ids)}}, {"full_name": 1, "role": 1})} if submitter_ids else {}
        for row in rows:
            row["submitter"] = _plain(submitters.get(row.get("submitted_by"), {}))
        return rows, total

    def overview(self):
        users = self.db["users"]
        products = self.db["marketplace_products"]
        orders = self.db["orders"]
        payments = self.db["payments"]
        reports = self.db["disease_reports"]
        pesticides = self.db["pesticide_records"]
        count = lambda collection, query={}: collection.count_documents(query)
        counts = {
            "users": {role.lower(): count(users, {"role": role}) for role in ("FARMER", "BUYER", "AGRICULTURAL_OFFICER", "ADMIN")},
            "products": {"total": count(products), "active": count(products, {"is_active": True}), "inactive": count(products, {"is_active": False})},
            "orders": {"total": count(orders), **{state.lower(): count(orders, {"order_status": state}) for state in ("PENDING", "AWAITING_PAYMENT", "PAID", "PROCESSING", "READY_FOR_DELIVERY", "IN_TRANSIT", "DELIVERED", "COMPLETED", "CANCELLED", "DISPUTED")}},
            "payments": {"total": count(payments), "successful": count(payments, {"status": {"$in": ["SUCCEEDED", "SUCCEEDED_REVIEW"]}}), "pending": count(payments, {"status": {"$in": ["PENDING", "INITIATING", "INITIATED"]}}), "failed": count(payments, {"status": {"$in": ["FAILED", "INITIATION_FAILED"]}})},
            "disease_reports": count(reports),
            "pending_officer_reviews": count(reports, {"case_status": "REVIEW_REQUESTED"}),
            "pending_pesticide_reviews": count(pesticides, {"review_status": "PENDING_REVIEW"}),
        }
        return {"counts": counts, "trends": {"users": self._monthly(users), "products": self._monthly(products), "orders": self._monthly(orders), "payments": self._monthly(payments), "market_prices": self._monthly(self.db["market_prices"]), "advisories": self._monthly(self.db["advisories"])}, "disease_by_condition": self._group(reports, "predicted_label"), "disease_by_crop": self._group(reports, "crop_name"), "marketplace_by_county": self._group(products, "county", {"is_active": True}), "payment_statuses": self._group(payments, "status"), "order_statuses": self._group(orders, "order_status")}

    @staticmethod
    def _monthly(collection):
        return [_plain(row) for row in collection.aggregate([{"$match": {"created_at": {"$type": "date"}}}, {"$group": {"_id": {"$dateToString": {"format": "%Y-%m", "date": "$created_at"}}, "count": {"$sum": 1}}}, {"$sort": {"_id": -1}}, {"$limit": 12}, {"$sort": {"_id": 1}}])]

    @staticmethod
    def _group(collection, field: str, query=None):
        pipeline = [{"$match": query or {}}, {"$group": {"_id": {"$ifNull": [f"${field}", "Unknown"]}, "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 12}]
        return [_plain(row) for row in collection.aggregate(pipeline)]

    def append_audit(self, *, actor_id: str, action: str, method: str, resource: str, status_code: int):
        self.db["audit_logs"].insert_one({"actor_id": ObjectId(actor_id), "action": action, "method": method, "resource": resource[:200], "status_code": status_code, "succeeded": 200 <= status_code < 400, "timestamp": datetime.now(timezone.utc)})

    def list_audit(self, *, actor_id: str | None, action: str | None, skip: int, limit: int):
        query = {}
        if actor_id and ObjectId.is_valid(actor_id):
            query["actor_id"] = ObjectId(actor_id)
        if action:
            query["action"] = action
        return self._page(self.db["audit_logs"], query, skip=skip, limit=limit, sort="timestamp")
