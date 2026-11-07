from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from app.models.payment import PaymentRecordStatus
from app.repositories.farmer_repository import public_document


class PaymentConflictError(Exception):
    """An idempotency key or active order payment already exists with different data."""


class PaymentRepository:
    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index("idempotency_key", unique=True, name="uq_payments_idempotency")
        self.collection.create_index("checkout_request_id", unique=True, sparse=True, name="uq_payments_checkout")
        self.collection.create_index("provider_receipt", unique=True, sparse=True, name="uq_payments_receipt")
        self.collection.create_index("active_order_id", unique=True, sparse=True, name="uq_payments_active_order")
        self.collection.create_index([("buyer_id", 1), ("created_at", -1)], name="ix_payments_buyer_created")

    @staticmethod
    def _public(document: dict | None) -> dict | None:
        if document is None:
            return None
        result = public_document(document)
        for key in ("order_id", "buyer_id"):
            if key in result:
                result[key] = str(result[key])
        result.pop("active_order_id", None)
        result.pop("idempotency_key", None)
        result.pop("merchant_request_id", None)
        result.pop("callback_phone_number", None)
        result.pop("callback_amount_kes", None)
        return result

    def create_pending(self, values: dict) -> dict:
        now = datetime.now(timezone.utc)
        document = {
            **values,
            "order_id": ObjectId(values["order_id"]),
            "buyer_id": ObjectId(values["buyer_id"]),
            "active_order_id": ObjectId(values["order_id"]),
            "status": PaymentRecordStatus.PENDING.value,
            "currency": "KES",
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            prior = self.collection.find_one({"idempotency_key": values["idempotency_key"]})
            if prior:
                if (
                    str(prior["order_id"]) == values["order_id"]
                    and prior["amount_kes"] == values["amount_kes"]
                    and prior["phone_number"] == values["phone_number"]
                ):
                    return self._public(prior)
                raise PaymentConflictError from exc
            raise PaymentConflictError from exc
        document["_id"] = result.inserted_id
        return self._public(document)

    def get(self, payment_id: str) -> dict | None:
        return self._public(self.collection.find_one({"_id": ObjectId(payment_id)}))

    def get_by_checkout(self, checkout_request_id: str) -> dict | None:
        return self._public(self.collection.find_one({"checkout_request_id": checkout_request_id}))

    def get_by_idempotency(self, key: str) -> dict | None:
        return self._public(self.collection.find_one({"idempotency_key": key}))

    def claim_initiation(self, payment_id: str) -> dict | None:
        doc = self.collection.find_one_and_update(
            {"_id": ObjectId(payment_id), "status": PaymentRecordStatus.PENDING.value},
            {"$set": {"status": PaymentRecordStatus.INITIATING.value, "updated_at": datetime.now(timezone.utc)}},
            return_document=ReturnDocument.AFTER,
        )
        return self._public(doc)

    def set_initiated(self, payment_id: str, merchant_request_id: str, checkout_request_id: str) -> dict | None:
        doc = self.collection.find_one_and_update(
            {"_id": ObjectId(payment_id), "status": PaymentRecordStatus.INITIATING.value},
            {"$set": {
                "status": PaymentRecordStatus.INITIATED.value,
                "merchant_request_id": merchant_request_id,
                "checkout_request_id": checkout_request_id,
                "updated_at": datetime.now(timezone.utc),
            }},
            return_document=ReturnDocument.AFTER,
        )
        return self._public(doc)

    def set_initiation_failed(self, payment_id: str, safe_reason: str) -> None:
        self.collection.update_one(
            {"_id": ObjectId(payment_id), "status": PaymentRecordStatus.INITIATING.value},
            {"$set": {"status": PaymentRecordStatus.INITIATION_FAILED.value, "failure_reason": safe_reason, "updated_at": datetime.now(timezone.utc)}},
        )

    def complete_callback(
        self,
        payment_id: str,
        *,
        status: PaymentRecordStatus,
        receipt: str | None,
        callback_amount: int,
        callback_phone: str | None,
        failure_reason: str | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        fields = {
            "status": status.value,
            "callback_amount_kes": callback_amount,
            "callback_phone_number": callback_phone,
            "failure_reason": failure_reason,
            "updated_at": now,
        }
        if receipt is not None:
            fields["provider_receipt"] = receipt
        doc = self.collection.find_one_and_update(
            {"_id": ObjectId(payment_id), "status": {"$in": [PaymentRecordStatus.INITIATING.value, PaymentRecordStatus.INITIATED.value]}},
            {
                "$set": {
                    **fields,
                },
                "$unset": {"active_order_id": "", **({} if receipt is not None else {"provider_receipt": ""})},
            },
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            existing = self.collection.find_one({"_id": ObjectId(payment_id)})
            if (
                existing
                and existing.get("status") == status.value
                and existing.get("provider_receipt") == receipt
                and existing.get("callback_amount_kes") == callback_amount
                and existing.get("callback_phone_number") == callback_phone
            ):
                return self._public(existing)
            raise PaymentConflictError
        return self._public(doc)

    def list_for_buyer(self, buyer_id: str, *, skip: int, limit: int) -> tuple[list[dict], int]:
        query = {"buyer_id": ObjectId(buyer_id)}
        total = self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(doc) for doc in cursor], total

    def list_all(self, *, skip: int, limit: int) -> tuple[list[dict], int]:
        total = self.collection.count_documents({})
        cursor = self.collection.find({}).sort("created_at", -1).skip(skip).limit(limit)
        return [self._public(doc) for doc in cursor], total
