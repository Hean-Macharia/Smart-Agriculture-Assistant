from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.transaction import LedgerEventType


class LedgerEventPublic(BaseModel):
    id: str
    order_id: str
    payment_id: str | None = None
    event_type: LedgerEventType
    amount_kes: int
    currency: str
    timestamp: datetime
    provider_reference: str | None = None
    status: str

    model_config = ConfigDict(extra="forbid")


class LedgerListResponse(BaseModel):
    items: list[LedgerEventPublic]
    total: int
