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


class DeliveryEventPublic(BaseModel):
    status: DeliveryStatus
    at: datetime
    by: str
    note: str | None = None


class DeliveryPublic(BaseModel):
    id: str
    order_id: str
    buyer_id: str
    seller_id: str
    status: DeliveryStatus
    carrier_name: str | None = None
    carrier_phone: str | None = None
    tracking_reference: str | None = None
    events: list[DeliveryEventPublic]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class DeliveryListResponse(BaseModel):
    items: list[DeliveryPublic]
    total: int
    limit: int
    offset: int
