from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.delivery import DeliveryStatus


class DeliveryCreate(BaseModel):
    carrier_name: str | None = Field(default=None, max_length=120)
    carrier_phone: str | None = Field(default=None, max_length=20)
    tracking_reference: str | None = Field(default=None, max_length=120)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DeliveryStatusUpdate(BaseModel):
    status: DeliveryStatus
    note: str | None = Field(default=None, max_length=500)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DeliveryPublic(BaseModel):
    id: str
    order_id: str
    buyer_id: str
    seller_id: str
    status: DeliveryStatus
    carrier_name: str | None = None
    carrier_phone: str | None = None
    tracking_reference: str | None = None
    events: list[dict]
    created_at: datetime
    updated_at: datetime


class DeliveryListResponse(BaseModel):
    items: list[DeliveryPublic]
    total: int
    limit: int
    offset: int
