from datetime import datetime, timezone

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from app.repositories.farmer_repository import public_document


class TransactionLedgerRepository:
    """Append-only financial event log. No update or delete methods are exposed."""

    def __init__(self, collection: Collection):
        self.collection = collection
        self.collection.create_index("event_key", unique=True, name="uq_ledger_event_key")
        self.collection.create_index([("order_id", 1), ("timestamp", 1)], name="ix_ledger_order_time")

    @staticmethod
    def _public(document: dict | None) -> dict | None:
        if document is None:
            return None
        result = public_document(document)
        result["order_id"] = str(result["order_id"])
        if result.get("payment_id") is not None:
            result["payment_id"] = str(result["payment_id"])
        result.pop("event_key", None)
        return result

    def append(self, event: dict) -> dict:
        document = {
            **event,
            "order_id": ObjectId(event["order_id"]),
            "payment_id": ObjectId(event["payment_id"]) if event.get("payment_id") else None,
            "currency": "KES",
            "timestamp": datetime.now(timezone.utc),
        }
        try:
            result = self.collection.insert_one(document)
            document["_id"] = result.inserted_id
            return self._public(document)
        except DuplicateKeyError:
            prior = self.collection.find_one({"event_key": event["event_key"]})
            if prior:
                same = (
                    str(prior["order_id"]) == event["order_id"]
                    and (str(prior.get("payment_id")) if prior.get("payment_id") else None) == event.get("payment_id")
                    and prior["event_type"] == event["event_type"]
                    and prior["amount_kes"] == event["amount_kes"]
                    and prior.get("provider_reference") == event.get("provider_reference")
                    and prior["status"] == event["status"]
                )
                if same:
                    return self._public(prior)
                raise ValueError("Ledger idempotency key was reused with different financial event data")
            raise

    def list_for_order(self, order_id: str) -> list[dict]:
        docs = self.collection.find({"order_id": ObjectId(order_id)}).sort("timestamp", 1)
        return [self._public(doc) for doc in docs]
