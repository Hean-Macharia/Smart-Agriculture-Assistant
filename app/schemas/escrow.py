from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.escrow import CustodyStatus, EscrowStatus


class EscrowPublic(BaseModel):
    id: str
    order_id: str
    payment_id: str
    provider: str
    status: EscrowStatus
    custody_status: CustodyStatus
    actual_funds_safeguarded: bool
    amount_kes: int
    commission_kes: int
    seller_amount_kes: int
    provider_reference: str | None = None
    last_action_reference: str | None = None
    refund_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class RefundRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EscrowActionResponse(BaseModel):
    status: str
    message: str
    escrow: EscrowPublic
