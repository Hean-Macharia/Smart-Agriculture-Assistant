"""User persistence. Password hashes are stored only in the users collection."""

from datetime import datetime, timezone
from threading import Lock

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

_indexes_ready = False
_indexes_lock = Lock()


class UserConflictError(Exception):
    """Email, phone, or bootstrap-admin uniqueness constraint was violated."""


class UserRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.ensure_indexes()

    def ensure_indexes(self) -> None:
        global _indexes_ready
        if _indexes_ready:
            return
        with _indexes_lock:
            if _indexes_ready:
                return
            self.collection.create_index("email", unique=True, name="uq_users_email")
            self.collection.create_index("phone", unique=True, name="uq_users_phone")
            self.collection.create_index([("role", 1), ("is_active", 1)], name="ix_users_role_active")
            self.collection.create_index(
                "bootstrap_admin",
                unique=True,
                partialFilterExpression={"bootstrap_admin": True},
                name="uq_bootstrap_admin",
            )
            _indexes_ready = True

    def create_user(self, values: dict, *, bootstrap_admin: bool = False) -> dict:
        now = datetime.now(timezone.utc)
        document = {
            **values,
            "is_active": True,
            "bootstrap_admin": bootstrap_admin,
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise UserConflictError from exc
        document["_id"] = result.inserted_id
        return document

    def get_by_email(self, email: str) -> dict | None:
        return self.collection.find_one({"email": email})

    def get_by_id(self, user_id: str) -> dict | None:
        try:
            object_id = ObjectId(user_id)
        except (InvalidId, TypeError):
            return None
        return self.collection.find_one({"_id": object_id})

    def count_admins(self) -> int:
        return self.collection.count_documents({"role": "ADMIN"})

    def list_users(self, *, skip: int, limit: int, role: str | None = None) -> tuple[list[dict], int]:
        query = {"role": role} if role else {}
        total = self.collection.count_documents(query)
        items = list(self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit))
        return items, total

    def update_profile(self, user_id: str, changes: dict) -> dict | None:
        try:
            object_id = ObjectId(user_id)
        except (InvalidId, TypeError):
            return None
        try:
            self.collection.update_one(
                {"_id": object_id},
                {"$set": {**changes, "updated_at": datetime.now(timezone.utc)}},
            )
        except DuplicateKeyError as exc:
            raise UserConflictError from exc
        return self.collection.find_one({"_id": object_id})
