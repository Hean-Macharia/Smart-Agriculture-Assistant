"""Consent, inbound-message replay protection and SMS sender rate limits."""

from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.models.notification import NotificationEvent


class SmsPreferencesRepository:
    def __init__(self, database: Database):
        self.preferences: Collection = database["sms_preferences"]
        self.inbound: Collection = database["sms_inbound_requests"]
        self.rate_limits: Collection = database["sms_rate_limits"]
        self.preferences.create_index("phone_number", unique=True, name="uq_sms_preferences_phone")
        self.preferences.create_index("user_id", unique=True, sparse=True, name="uq_sms_preferences_user")
        self.inbound.create_index("provider_message_id", unique=True, name="uq_sms_inbound_provider_message")
        self.inbound.create_index([("phone_number", 1), ("created_at", -1)], name="ix_sms_inbound_phone_time")
        self.rate_limits.create_index("expires_at", expireAfterSeconds=0, name="ttl_sms_rate_limit")

    @staticmethod
    def _public(document: dict | None, *, phone_number: str | None = None) -> dict:
        if document is None:
            return {
                "phone_number": phone_number or "",
                "consented": False,
                "consented_at": None,
                "opted_out_at": None,
                "language": "en",
                "categories": [],
                "phone_verified": False,
                "consent_history": [],
            }
        return {
            "phone_number": document.get("phone_number", phone_number or ""),
            "consented": bool(document.get("consented", False)),
            "consented_at": document.get("consented_at"),
            "opted_out_at": document.get("opted_out_at"),
            "language": document.get("language", "en"),
            "categories": document.get("categories", []),
            "phone_verified": bool(document.get("phone_verified", False)),
            "consent_history": document.get("consent_history", []),
        }

    def get_for_user(self, user_id: str, phone_number: str) -> dict:
        return self._public(self.preferences.find_one({"user_id": ObjectId(user_id)}), phone_number=phone_number)

    def get_for_phone(self, phone_number: str) -> dict | None:
        return self.preferences.find_one({"phone_number": phone_number})

    def save_for_user(self, *, user_id: str, phone_number: str, consented: bool, language: str, categories: list[str]) -> dict:
        now = datetime.now(timezone.utc)
        user_object_id = ObjectId(user_id)
        previous = self.preferences.find_one({"user_id": user_object_id}) or self.preferences.find_one({"phone_number": phone_number})
        phone_changed = bool(previous and previous.get("phone_number") != phone_number)
        if phone_changed:
            consented = False
            categories = []
        action = "CONSENT_GRANTED" if consented else "CONSENT_WITHDRAWN"
        history = []
        if phone_changed:
            history.append({"action": "PHONE_CHANGED_RECONSENT_REQUIRED", "source": "profile_update", "at": now})
        history.append({"action": action, "source": "authenticated_settings", "at": now})
        update = {
            "$set": {
                "user_id": user_object_id,
                "phone_number": phone_number,
                "consented": consented,
                "consented_at": now if consented else (previous or {}).get("consented_at"),
                "opted_out_at": None if consented else now,
                "language": language,
                "categories": categories if consented else [],
                "updated_at": now,
            },
            "$setOnInsert": {"phone_verified": False, "created_at": now},
            "$push": {"consent_history": {"$each": history}},
        }
        query = {"_id": previous["_id"]} if previous else {"phone_number": phone_number}
        try:
            result = self.preferences.find_one_and_update(query, update, upsert=True, return_document=ReturnDocument.AFTER)
        except DuplicateKeyError:
            result = self.preferences.find_one({"user_id": user_object_id})
            if result is None:
                raise
        return self._public(result, phone_number=phone_number)

    def set_phone_consent(self, *, phone_number: str, consented: bool, source: str) -> dict:
        now = datetime.now(timezone.utc)
        action = "CONSENT_GRANTED" if consented else "CONSENT_WITHDRAWN"
        query = {"phone_number": phone_number}
        update = {
            "$set": {
                "phone_number": phone_number,
                "consented": consented,
                "opted_out_at": None if consented else now,
                "categories": [event.value for event in NotificationEvent] if consented else [],
                "updated_at": now,
            },
            "$setOnInsert": {"phone_verified": False, "language": "en", "created_at": now},
            "$push": {"consent_history": {"action": action, "source": source, "at": now}},
        }
        if consented:
            update["$set"]["consented_at"] = now
        result = self.preferences.find_one_and_update(query, update, upsert=True, return_document=ReturnDocument.AFTER)
        return result

    def set_phone_language(self, *, phone_number: str, language: str, source: str) -> dict:
        now = datetime.now(timezone.utc)
        return self.preferences.find_one_and_update(
            {"phone_number": phone_number},
            {
                "$set": {"language": language, "updated_at": now},
                "$setOnInsert": {"phone_verified": False, "consented": False, "categories": [], "created_at": now},
                "$push": {"consent_history": {"action": f"LANGUAGE_{language.upper()}", "source": source, "at": now}},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    def permits(self, *, user_id: str, phone_number: str, event: str) -> bool:
        preferences = self.preferences.find_one({"user_id": ObjectId(user_id)})
        return bool(
            preferences
            and preferences.get("phone_number") == phone_number
            and preferences.get("consented") is True
            and event in preferences.get("categories", [])
        )

    def accept_inbound(self, *, provider_message_id: str, phone_number: str, command: str, hourly_limit: int) -> bool:
        now = datetime.now(timezone.utc)
        hour = now.replace(minute=0, second=0, microsecond=0)
        bucket_id = f"{phone_number}:{hour.isoformat()}"
        try:
            self.rate_limits.find_one_and_update(
                {"_id": bucket_id, "count": {"$lt": hourly_limit}},
                {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": hour + timedelta(hours=2)}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            return False
        try:
            self.inbound.insert_one({
                "provider_message_id": provider_message_id,
                "phone_number": phone_number,
                "command": command[:120],
                "created_at": now,
            })
        except DuplicateKeyError:
            return False
        return True

