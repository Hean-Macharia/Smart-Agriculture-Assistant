from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.dispute import DisputeDecision, DisputeReason, DisputeStatus
from app.models.order import OrderStatus


class DisputeCreate(BaseModel):
    order_id: str = Field(pattern=r"^[0-9a-fA-F]{24}$")
    reason: DisputeReason
    description: str = Field(min_length=10, max_length=3000)
    evidence_urls: list[HttpUrl] = Field(default_factory=list, max_length=10)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DisputeReview(BaseModel):
    status: DisputeStatus
    decision: DisputeDecision | None = None
    resolution: str = Field(min_length=10, max_length=3000)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DisputeDecisionPublic(BaseModel):
    admin_id: str
    status: DisputeStatus
    decision: DisputeDecision | None = None
    resolution: str
    at: datetime

    model_config = ConfigDict(extra="forbid")


class DisputePublic(BaseModel):
    id: str
    order_id: str
    buyer_id: str
    seller_id: str
    raised_by: str
    reason: DisputeReason
    description: str
    evidence_urls: list[str]
    status: DisputeStatus
    decisions: list[DisputeDecisionPublic]
    created_at: datetime
    updated_at: datetime
    previous_order_status: OrderStatus | None = Field(default=None, exclude=True)

    model_config = ConfigDict(extra="forbid")


class DisputeListResponse(BaseModel):
    items: list[DisputePublic]
    total: int
    limit: int
    offset: int
