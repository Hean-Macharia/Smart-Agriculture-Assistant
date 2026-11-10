from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.order import OrderStatus, PaymentStatus


class DeliveryInformation(BaseModel):
    recipient_name: str = Field(min_length=2, max_length=120)
    recipient_phone: str = Field(min_length=10, max_length=20)
    county: str = Field(min_length=2, max_length=80)
    sub_county: str = Field(min_length=2, max_length=80)
    location: str = Field(min_length=2, max_length=200)
    instructions: str | None = Field(default=None, max_length=500)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrderCreate(BaseModel):
    product_id: str = Field(pattern=r"^[0-9a-fA-F]{24}$")
    quantity: int = Field(gt=0, le=2_000_000_000)
    delivery_information: DeliveryInformation

    model_config = ConfigDict(extra="forbid")


class OrderPublic(BaseModel):
    id: str
    buyer_id: str
    seller_id: str
    product_id: str
    product_name: str
    quantity: int
    unit: str
    unit_price_kes: int
    total_amount_kes: int
    payment_id: str | None = None
    delivery_information: DeliveryInformation
    payment_status: PaymentStatus
    order_status: OrderStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class OrderListResponse(BaseModel):
    items: list[OrderPublic]
    total: int
    limit: int
    offset: int


class OrderStatusUpdate(BaseModel):
    order_status: OrderStatus

    model_config = ConfigDict(extra="forbid")
